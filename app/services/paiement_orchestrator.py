from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus
from app.models.paiements import (
    CotisationMensuelle,
    CotisationStatut,
    ParametrePaiementCode,
    PeriodePaiement,
    StatutTransactionKopar,
    TransactionKopar,
    TypeTransactionKopar,
)
from app.repositories.adhesions import AdhesionRepository
from app.repositories.paiements import (
    CotisationMensuelleRepository,
    ParametrePaiementRepository,
    TransactionKoparRepository,
)
from app.services.adhesion_mail_templates import (
    build_cotisation_paiement_confirme,
    build_paiement_adhesion_confirme,
)
from app.services.kopar import (
    KoparClient,
    KoparPaiementInitie,
    verify_kopar_signature,
    webhook_statut_to_enum,
)
from app.services.mail import send_email_best_effort
from app.services.paiements import ParametresPaiementService
from app.services.qr_code import QRCodeStorageService


@dataclass(frozen=True)
class WebhookProcessed:
    ok: bool
    code: str
    message: str
    transaction_id: uuid.UUID | None = None
    action: str | None = None


class PaiementOrchestratorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.kopar = KoparClient()
        self.transactions = TransactionKoparRepository(session)
        self.cotisations = CotisationMensuelleRepository(session)
        self.adhesions = AdhesionRepository(session)
        self.qr = QRCodeStorageService()

    # ------------------------------------------------------------------ utils
    def _public_url(self, path: str) -> str:
        base = self.settings.public_base_url or self.settings.api_base_url or ""
        base = base.rstrip("/")
        if path.startswith("http"):
            return path
        return base + path

    def _build_urls(
        self, *, type_tx: str, adhesion_id: uuid.UUID, cotisation_id: uuid.UUID | None
    ) -> tuple[str, str, str]:
        ipn = self._public_url(f"/api/v1/paiements/webhook/kopar")
        base_front = (self.settings.public_base_url or "").rstrip("/") or (
            (self.settings.api_base_url or "").rstrip("/")
        )
        if cotisation_id:
            ok_rel = f"/paiement/succes/cotisation/{cotisation_id}"
            cancel_rel = f"/paiement/annuler/cotisation/{cotisation_id}"
        else:
            ok_rel = f"/paiement/succes/adhesion/{adhesion_id}"
            cancel_rel = f"/paiement/annuler/adhesion/{adhesion_id}"
        return ipn, base_front + ok_rel, base_front + cancel_rel

    async def _creer_transaction_db(
        self,
        *,
        type_tx: TypeTransactionKopar,
        adhesion_id: uuid.UUID,
        cotisation_id: uuid.UUID | None,
        command_ref: str,
        command_name: str,
        montant: int,
        kopar_token: str,
        raw_request: dict,
        raw_response: dict,
        customer_first_name: str | None = None,
        customer_last_name: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
        country_code: str = "SN",
        ipn_url: str | None = None,
        success_url: str | None = None,
        cancel_url: str | None = None,
        custom_fields: dict | None = None,
        periode_mois: int | None = None,
        premiere_annee_couverte: int | None = None,
        premier_mois_couverte: int | None = None,
    ) -> TransactionKopar:
        tx = TransactionKopar(
            kopar_token=kopar_token,
            type_transaction=type_tx,
            adhesion_id=adhesion_id,
            cotisation_id=cotisation_id,
            periode_mois=periode_mois,
            premiere_annee_couverte=premiere_annee_couverte,
            premier_mois_couverte=premier_mois_couverte,
            command_ref=command_ref,
            command_name=command_name,
            montant=montant,
            statut=StatutTransactionKopar.new,
            customer_first_name=customer_first_name,
            customer_last_name=customer_last_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            country_code=country_code,
            ipn_url=ipn_url,
            success_url=success_url,
            cancel_url=cancel_url,
            custom_fields=custom_fields,
            raw_request=raw_request,
            raw_response=raw_response,
        )
        return await self.transactions.create(tx)

    # ---------------------------------------------------------------- adhesion
    async def initier_paiement_adhesion(
        self,
        adhesion_id: uuid.UUID,
        *,
        force: bool = False,
        service: str | None = None,
        override_prenom: str | None = None,
        override_nom: str | None = None,
        override_telephone: str | None = None,
        override_email: str | None = None,
        override_cni: str | None = None,
        override_date_naissance: date | None = None,
        override_lieu_naissance: str | None = None,
        override_adresse: str | None = None,
    ) -> KoparPaiementInitie:
        adhesion = await self.adhesions.get_by_id(adhesion_id)
        if not adhesion:
            raise HTTPException(status_code=404, detail="Adhésion introuvable")
        if adhesion.paiement_confirme and not force:
            raise HTTPException(status_code=409, detail="Paiement déjà effectué")
        if adhesion.montant_adhesion <= 0:
            raise HTTPException(
                status_code=400, detail="Montant adhésion invalide sur l'adhésion"
            )

        prenom = (override_prenom or adhesion.prenom or "").strip() or adhesion.prenom
        nom = (override_nom or adhesion.nom or "").strip() or adhesion.nom
        telephone = (override_telephone or adhesion.tel_mobile or "").strip() or adhesion.tel_mobile
        email = (override_email or adhesion.email or "").strip() or adhesion.email
        cni = (override_cni or getattr(adhesion, "cni", None) or "").strip() or None
        date_naissance = override_date_naissance or getattr(adhesion, "date_naissance", None)
        lieu_naissance = (
            (override_lieu_naissance or getattr(adhesion, "lieu_naissance", None) or "").strip()
            or None
        )
        adresse = (
            (override_adresse or getattr(adhesion, "adresse", None) or "").strip()
            or None
        )
        country_code = "SN" if not adhesion.est_diaspora else "SN"

        command_ref = f"ADH-{str(adhesion_id)}"
        prev_txs_adh = await self.transactions.get_by_command_ref(command_ref)
        if prev_txs_adh:
            prev_adh = sorted(prev_txs_adh, key=lambda t: t.created_at or datetime.min, reverse=True)[0]
            if prev_adh.kopar_token:
                raw_url_adh = ""
                try:
                    if isinstance(prev_adh.raw_response, dict):
                        raw_url_adh = str(prev_adh.raw_response.get("paymentUrl") or prev_adh.raw_response.get("payment_url") or "").strip()
                except Exception:
                    raw_url_adh = ""
                prev_payment_url_adh = raw_url_adh or f"{self.settings.kopar_base_url.rstrip('/')}/payment/orders/{prev_adh.kopar_token}"
                return KoparPaiementInitie(
                    token=prev_adh.kopar_token,
                    payment_url=prev_payment_url_adh,
                    qr_code=getattr(prev_adh, "qr_code", None),
                    montant=int(getattr(prev_adh, "montant", adhesion.montant_adhesion) or 0) or int(adhesion.montant_adhesion or 0),
                    devise=getattr(prev_adh, "devise", "XOF") or "XOF",
                    provider_response=prev_adh.raw_response or {},
                )
        command_name = "Adhésion MONCAP"
        ipn_url, success_url, cancel_url = self._build_urls(
            type_tx="adhesion", adhesion_id=adhesion_id, cotisation_id=None
        )
        custom_fields = {"adhesion_id": str(adhesion_id), "type": "adhesion"}
        initie = await self.kopar.creer_transaction(
            item_price=adhesion.montant_adhesion,
            command_name=command_name,
            command_ref=command_ref,
            ipn_url=ipn_url,
            success_url=success_url,
            cancel_url=cancel_url,
            first_name=prenom,
            last_name=nom,
            email=email,
            phone_number=telephone,
            country_code=country_code,
            currency="XOF",
            custom_fields=custom_fields,
            document_number=cni,
            document_type="CNI",
            birth_date=date_naissance,
            birth_place=lieu_naissance or "",
            city="",
            address=adresse or "",
            service_paiement=service,
        )
        service_effectif = service or "kopar_services_cross"
        mapping_bank = {
            "wave_checkout": "wave",
            "orange_money_sn": "orange_money",
            "wave_checkout_ci": "wave",
            "kopar_services_cross": "kopar_cross",
        }
        payment_method = mapping_bank.get(service_effectif, service_effectif)
        user_kyc_camel = {
            "firstName": prenom,
            "lastName": nom,
            "phoneNumber": telephone,
            "email": email,
            "documentNumber": cni,
            "documentType": "CNI" if cni else "",
            "birthDate": date_naissance.isoformat() if date_naissance else "",
            "birthPlace": lieu_naissance or "",
            "country": country_code,
            "city": "",
            "address": adresse or "",
        }
        bank_details_camel = {
            "paymentMethod": payment_method,
            "phone": telephone or "",
            "country": country_code or "SN",
            "currency": "XOF",
            "serviceId": service_effectif,
        }
        services_requierent_checkout = {"wave_checkout", "orange_money_sn", "wave_checkout_ci"}
        if service and service in services_requierent_checkout:
            initie = await self.kopar.checkout(
                initie.token,
                service,
                user_kyc=user_kyc_camel,
                bank_details=bank_details_camel,
                country_code=country_code,
                currency="XOF",
                phone_number=telephone,
            )
        raw_request_camel = {
            "itemPrice": adhesion.montant_adhesion,
            "commandName": command_name,
            "commandRef": command_ref,
            "ipnUrl": ipn_url,
            "successUrl": success_url,
            "cancelUrl": cancel_url,
            "firstName": prenom,
            "lastName": nom,
            "email": email,
            "phoneNumber": telephone,
            "countryCode": country_code,
            "currency": "XOF",
            "customFields": custom_fields,
            "userKyc": user_kyc_camel,
            "bankDetails": bank_details_camel,
        }
        await self._creer_transaction_db(
            type_tx=TypeTransactionKopar.adhesion,
            adhesion_id=adhesion_id,
            cotisation_id=None,
            command_ref=command_ref,
            command_name=command_name,
            montant=adhesion.montant_adhesion,
            kopar_token=initie.token,
            raw_request=raw_request_camel,
            raw_response=initie.provider_response or {"token": initie.token},
            customer_first_name=prenom,
            customer_last_name=nom,
            customer_email=email,
            customer_phone=telephone,
            ipn_url=ipn_url,
            success_url=success_url,
            cancel_url=cancel_url,
            custom_fields=custom_fields,
        )
        return initie

    # -------------------------------------------------------------- cotisation
    async def initier_paiement_cotisation(
        self,
        cotisation_id: uuid.UUID,
        *,
        force: bool = False,
        service: str | None = None,
    ) -> KoparPaiementInitie:
        return await self.initier_paiement_cotisation_periode(
            cotisation_id,
            periode_mois=PeriodePaiement.MENSUEL,
            force=force,
            service=service,
        )

    async def initier_paiement_cotisation_periode(
        self,
        premier_cotisation_id: uuid.UUID,
        *,
        periode_mois: int = PeriodePaiement.MENSUEL,
        force: bool = False,
        service: str | None = None,
    ) -> KoparPaiementInitie:
        periode = PeriodePaiement.normaliser(periode_mois)
        c = await self.cotisations.get_by_id(premier_cotisation_id)
        if not c:
            raise HTTPException(status_code=404, detail="Cotisation introuvable")
        adhesion = await self.adhesions.get_by_id(c.adhesion_id)
        if not adhesion:
            raise HTTPException(status_code=404, detail="Adhérent introuvable")
        liste_mois = self.cotisations.calculer_mois_consecutifs(c.annee, c.mois, periode)
        params_svc = ParametresPaiementService(self.session)
        premiere_an = int(getattr(adhesion, "premiere_annee_cotisation", None) or 0) or 0
        premiere_mo = int(getattr(adhesion, "premier_mois_cotisation", None) or 0) or 0
        try:
            regle_texte = await params_svc.get_regle_premiere_cotisation()
            if "jour_paiement_offert" in (regle_texte or "").lower():
                regle_offert = "premier_mois_offert"
            elif "premier" in (regle_texte or "").lower() and ("mois" in (regle_texte or "").lower() or "offert" in (regle_texte or "").lower()):
                regle_offert = "premier_mois_offert"
            else:
                regle_offert = "pas_de_mois_offert"
        except Exception:
            regle_offert = "pas_de_mois_offert"
        montant_ref_mois: int = 0
        try:
            montant_ref_mois = int(await params_svc.get_montant(ParametrePaiementCode.cotisation_mensuelle, date.today()))
        except Exception:
            montant_ref_mois = 0
        if montant_ref_mois <= 0:
            montant_ref_mois = int(self.settings.default_cotisation_mensuelle_fcfa or 5)
        for idx, (an, mo) in enumerate(liste_mois):
            existant = await self.cotisations.get_for_adherent_mois(c.adhesion_id, an, mo)
            if existant is None:
                await self.cotisations.get_or_create_for_adherent_mois(
                    c.adhesion_id,
                    an,
                    mo,
                    montant_defaut=montant_ref_mois,
                    devise="XOF",
                )
        if periode == 1 and c.statut == CotisationStatut.payee and not force:
            raise HTTPException(status_code=409, detail="Cotisation déjà payée")
        if periode > 1 and not force:
            all_suivants = []
            for (an, mo) in liste_mois[1:]:
                c_suiv = await self.cotisations.get_for_adherent_mois(c.adhesion_id, an, mo)
                all_suivants.append(c_suiv)
            if c.statut == CotisationStatut.payee and all(
                (x is not None and (x.statut.value if hasattr(x.statut, "value") else str(x.statut)) == "payee")
                for x in all_suivants if x is not None
            ):
                raise HTTPException(status_code=409, detail="Toutes les cotisations de la période sont déjà payées")
        montant_total: int = 0
        premier_mois_offert = bool(regle_offert == "premier_mois_offert" and premiere_an and premiere_mo)
        for idx, (an, mo) in enumerate(liste_mois):
            ligne = await self.cotisations.get_for_adherent_mois(c.adhesion_id, an, mo)
            if ligne is None:
                continue
            statut_val = ligne.statut.value if hasattr(ligne.statut, "value") else str(ligne.statut)
            if statut_val == "payee":
                continue
            est_offert = False
            if premier_mois_offert and idx == 0 and int(an) == premiere_an and int(mo) == premiere_mo:
                est_offert = True
            if est_offert:
                continue
            m_ligne = int(getattr(ligne, "montant", None) or 0)
            if m_ligne <= 0:
                m_ligne = montant_ref_mois
                try:
                    ligne.montant = m_ligne
                except Exception:
                    pass
            montant_total += int(m_ligne)
        if montant_total <= 0:
            montant_total = int(montant_ref_mois) * int(max(1, periode))
        suffixe_cmd = f"P{periode}" if periode > 1 else ""
        command_ref = f"COT{suffixe_cmd}-{str(c.id)}" if suffixe_cmd else f"COT-{str(c.id)}"
        if periode > 1:
            command_ref = f"COTP-{periode}-{str(c.id)}"
        prev_txs = await self.transactions.get_by_command_ref(command_ref)
        if prev_txs:
            prev = sorted(prev_txs, key=lambda t: t.created_at or datetime.min, reverse=True)[0]
            if prev.kopar_token:
                raw_url = ""
                try:
                    if isinstance(prev.raw_response, dict):
                        raw_url = str(prev.raw_response.get("paymentUrl") or prev.raw_response.get("payment_url") or "").strip()
                except Exception:
                    raw_url = ""
                prev_payment_url = raw_url or f"{self.settings.kopar_base_url.rstrip('/')}/payment/orders/{prev.kopar_token}"
                return KoparPaiementInitie(
                    token=prev.kopar_token,
                    payment_url=prev_payment_url,
                    qr_code=getattr(prev, "qr_code", None),
                    montant=int(getattr(prev, "montant", montant_total) or 0) or montant_total,
                    devise=getattr(prev, "devise", "XOF") or "XOF",
                    provider_response=prev.raw_response or {},
                )
        if periode == 1:
            command_name = f"Cotisation MONCAP {c.mois:02d}/{c.annee}"
        else:
            dernier_an, dernier_mo = liste_mois[-1]
            premier_label = f"{c.mois:02d}/{c.annee}"
            dernier_label = f"{dernier_mo:02d}/{dernier_an}"
            command_name = f"Cotisation MONCAP {PeriodePaiement.label(periode)} ({premier_label} → {dernier_label})"
        ipn_url, success_url, cancel_url = self._build_urls(
            type_tx="cotisation", adhesion_id=c.adhesion_id, cotisation_id=c.id
        )
        custom_fields = {
            "cotisation_id": str(c.id),
            "adhesion_id": str(c.adhesion_id),
            "annee": c.annee,
            "mois": c.mois,
            "type": "cotisation",
            "periode_mois": periode,
            "premiere_annee_couverte": c.annee,
            "premier_mois_couverte": c.mois,
        }
        cni_cot = getattr(adhesion, "cni", None) or ""
        ddn_cot = getattr(adhesion, "date_naissance", None)
        lieun_cot = getattr(adhesion, "lieu_naissance", None) or ""
        addr_cot = getattr(adhesion, "adresse", None) or ""
        country_code_cot = "SN" if not adhesion.est_diaspora else "SN"
        service_eff_cot = service or "kopar_services_cross"
        mapping_cot_bank = {
            "wave_checkout": "wave",
            "orange_money_sn": "orange_money",
            "wave_checkout_ci": "wave",
            "kopar_services_cross": "kopar_cross",
        }
        pay_method_cot = mapping_cot_bank.get(service_eff_cot, service_eff_cot)
        user_kyc_cot_before = {
            "firstName": adhesion.prenom,
            "lastName": adhesion.nom,
            "phoneNumber": adhesion.tel_mobile,
            "email": adhesion.email,
            "documentNumber": cni_cot,
            "documentType": "CNI" if cni_cot else "",
            "birthDate": ddn_cot.isoformat() if ddn_cot else "",
            "birthPlace": lieun_cot or "",
            "country": country_code_cot,
            "city": "",
            "address": addr_cot or "",
        }
        bank_details_cot_before = {
            "paymentMethod": pay_method_cot,
            "phone": adhesion.tel_mobile or "",
            "country": country_code_cot or "SN",
            "currency": c.devise or "XOF",
            "serviceId": service_eff_cot,
        }
        initie = await self.kopar.creer_transaction(
            item_price=montant_total,
            command_name=command_name,
            command_ref=command_ref,
            ipn_url=ipn_url,
            success_url=success_url,
            cancel_url=cancel_url,
            first_name=adhesion.prenom,
            last_name=adhesion.nom,
            email=adhesion.email,
            phone_number=adhesion.tel_mobile,
            country_code=country_code_cot,
            currency=c.devise or "XOF",
            custom_fields=custom_fields,
            document_number=cni_cot or None,
            document_type="CNI",
            birth_date=ddn_cot,
            birth_place=lieun_cot or "",
            city="",
            address=addr_cot or "",
            service_paiement=service,
        )
        services_requierent_checkout_cot = {"wave_checkout", "orange_money_sn", "wave_checkout_ci"}
        if service and service in services_requierent_checkout_cot:
            initie = await self.kopar.checkout(
                initie.token,
                service,
                user_kyc=user_kyc_cot_before,
                bank_details=bank_details_cot_before,
                country_code=country_code_cot,
                currency=c.devise or "XOF",
                phone_number=adhesion.tel_mobile,
            )
        user_kyc_cot = user_kyc_cot_before
        bank_details_cot = bank_details_cot_before
        raw_request_camel = {
            "itemPrice": montant_total,
            "commandName": command_name,
            "commandRef": command_ref,
            "ipnUrl": ipn_url,
            "successUrl": success_url,
            "cancelUrl": cancel_url,
            "firstName": adhesion.prenom,
            "lastName": adhesion.nom,
            "email": adhesion.email,
            "phoneNumber": adhesion.tel_mobile,
            "countryCode": "SN" if not adhesion.est_diaspora else "SN",
            "currency": c.devise or "XOF",
            "customFields": custom_fields,
            "userKyc": user_kyc_cot,
            "bankDetails": bank_details_cot,
        }
        await self._creer_transaction_db(
            type_tx=TypeTransactionKopar.cotisation,
            adhesion_id=c.adhesion_id,
            cotisation_id=c.id,
            command_ref=command_ref,
            command_name=command_name,
            montant=montant_total,
            kopar_token=initie.token,
            raw_request=raw_request_camel,
            raw_response=initie.provider_response or {"token": initie.token},
            customer_first_name=adhesion.prenom,
            customer_last_name=adhesion.nom,
            customer_email=adhesion.email,
            customer_phone=adhesion.tel_mobile,
            ipn_url=ipn_url,
            success_url=success_url,
            cancel_url=cancel_url,
            custom_fields=custom_fields,
            periode_mois=periode,
            premiere_annee_couverte=c.annee,
            premier_mois_couverte=c.mois,
        )
        return initie

    # ----------------------------------------------------------------- webhook
    async def processer_webhook_kopar(
        self,
        *,
        raw_body: str,
        signature: str,
        json_body: dict[str, Any],
        background_tasks: BackgroundTasks | None = None,
    ) -> WebhookProcessed:
        if not verify_kopar_signature(raw_body, signature, self.settings.kopar_private_key or ""):
            return WebhookProcessed(ok=False, code="INVALID_SIGNATURE", message="Signature HMAC invalide")

        kopar_status = str(json_body.get("status") or "").strip().lower()
        statut = webhook_statut_to_enum(kopar_status)
        command_ref = json_body.get("commandRef") or ""
        custom_fields_raw = json_body.get("customFields") or "{}"
        if isinstance(custom_fields_raw, str):
            try:
                custom_fields = json.loads(custom_fields_raw)
            except Exception:
                custom_fields = {}
        else:
            custom_fields = custom_fields_raw if isinstance(custom_fields_raw, dict) else {}
        tx_type = custom_fields.get("type")

        tx = None
        if command_ref:
            matches = await self.transactions.get_by_command_ref(command_ref)
            if matches:
                tx = matches[0]

        if not tx:
            adhesion_id = custom_fields.get("adhesion_id")
            if adhesion_id:
                matches2 = await self.transactions.get_by_command_ref(f"ADH-{adhesion_id}")
                if matches2:
                    tx = matches2[0]
        if not tx:
            return WebhookProcessed(
                ok=False,
                code="TRANSACTION_NOT_FOUND",
                message=f"Aucune transaction trouvée pour ref {command_ref}",
            )

        await self.transactions.update_after_webhook(
            tx.id,
            statut,
            webhook_body=json_body,
            customer_email=json_body.get("email"),
            customer_phone=json_body.get("phoneNumber"),
        )

        action = None
        if statut == StatutTransactionKopar.success:
            if tx.type_transaction == TypeTransactionKopar.adhesion:
                await self._appliquer_paiement_adhesion_success(tx, background_tasks)
                action = "adhesion_confirmee"
            elif tx.type_transaction == TypeTransactionKopar.cotisation:
                await self._appliquer_paiement_cotisation_success(tx, background_tasks)
                action = "cotisation_confirmee"

        return WebhookProcessed(
            ok=True,
            code="OK",
            message="Webhook traité",
            transaction_id=tx.id,
            action=action,
        )

    async def _appliquer_paiement_adhesion_success(
        self,
        tx: TransactionKopar,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        if not tx.adhesion_id:
            return
        adhesion = await self.adhesions.get_by_id(tx.adhesion_id)
        if not adhesion:
            return
        if adhesion.paiement_confirme:
            return
        adhesion.paiement_confirme = True
        adhesion.reference_paiement = (
            adhesion.reference_paiement or tx.kopar_token
        )
        await self.session.flush()

        if (
            self.settings.mail_enabled
            and adhesion.email
            and background_tasks is not None
        ):
            try:
                subject, text, html = build_paiement_adhesion_confirme(
                    adhesion=adhesion,
                    base_url=self.settings.public_base_url or "",
                    montant=tx.montant,
                    reference=tx.kopar_token,
                )
                background_tasks.add_task(
                    send_email_best_effort,
                    to=adhesion.email,
                    subject=subject,
                    text=text,
                    html=html,
                    settings=self.settings,
                )
            except Exception:
                pass

    async def appliquer_paiement_cotisation_success(
        self,
        tx: TransactionKopar,
        background_tasks: BackgroundTasks | None = None,
    ) -> list[CotisationMensuelle]:
        """
        Applique la validation Kopar success sur la transaction.
        - Utilise mark_paid_periode() (idempotent).
        - Retourne la liste des lignes marquées payées (vide si déjà payée).
        - PUBLIC : réutilisable depuis la réconciliation CLI (qui n'a pas BackgroundTasks).
        """
        if not tx.cotisation_id:
            return []
        lignes_payees = await self.cotisations.mark_paid_periode(
            tx,
            reference_paiement=tx.kopar_token,
            mode_paiement=tx.service or "kopar",
        )
        if not lignes_payees:
            return []
        adhesion = await self.adhesions.get_by_id(lignes_payees[0].adhesion_id)
        if (
            adhesion
            and self.settings.mail_enabled
            and adhesion.email
            and background_tasks is not None
        ):
            try:
                mois_couverts: list[tuple[int, int]] = []
                montant_total = 0
                for cc in lignes_payees:
                    mois_couverts.append((int(cc.annee), int(cc.mois)))
                    montant_total += int(getattr(cc, "montant", None) or 0)
                if not mois_couverts:
                    if tx.premiere_annee_couverte and tx.premier_mois_couverte:
                        periode = PeriodePaiement.normaliser(tx.periode_mois)
                        mois_couverts = self.cotisations.calculer_mois_consecutifs(
                            int(tx.premiere_annee_couverte),
                            int(tx.premier_mois_couverte),
                            periode,
                        )
                if montant_total <= 0:
                    montant_total = int(getattr(tx, "montant", None) or 0)
                subject, text, html = build_cotisation_paiement_confirme(
                    adhesion=adhesion,
                    base_url=self.settings.public_base_url or "",
                    mois_couverts=mois_couverts,
                    montant_total=montant_total,
                    reference=tx.kopar_token,
                )
                background_tasks.add_task(
                    send_email_best_effort,
                    to=adhesion.email,
                    subject=subject,
                    text=text,
                    html=html,
                    settings=self.settings,
                )
            except Exception:
                pass
        return lignes_payees

    async def _appliquer_paiement_cotisation_success(
        self,
        tx: TransactionKopar,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        """Wrapper privé rétro-compatible (anciens appels)."""
        await self.appliquer_paiement_cotisation_success(tx, background_tasks)
