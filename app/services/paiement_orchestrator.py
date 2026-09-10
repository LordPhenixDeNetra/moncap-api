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
    ) -> TransactionKopar:
        tx = TransactionKopar(
            kopar_token=kopar_token,
            type_transaction=type_tx,
            adhesion_id=adhesion_id,
            cotisation_id=cotisation_id,
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
        c = await self.cotisations.get_by_id(cotisation_id)
        if not c:
            raise HTTPException(status_code=404, detail="Cotisation introuvable")
        if c.statut == CotisationStatut.payee and not force:
            raise HTTPException(status_code=409, detail="Cotisation déjà payée")
        adhesion = await self.adhesions.get_by_id(c.adhesion_id)
        if not adhesion:
            raise HTTPException(status_code=404, detail="Adhérent introuvable")
        command_ref = f"COT-{str(c.id)}"
        command_name = f"Cotisation MONCAP {c.mois:02d}/{c.annee}"
        ipn_url, success_url, cancel_url = self._build_urls(
            type_tx="cotisation", adhesion_id=c.adhesion_id, cotisation_id=c.id
        )
        custom_fields = {
            "cotisation_id": str(c.id),
            "adhesion_id": str(c.adhesion_id),
            "annee": c.annee,
            "mois": c.mois,
            "type": "cotisation",
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
            item_price=c.montant,
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
            "itemPrice": c.montant,
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
            montant=c.montant,
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

    async def _appliquer_paiement_cotisation_success(
        self,
        tx: TransactionKopar,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        if not tx.cotisation_id:
            return
        c = await self.cotisations.mark_paid(
            tx.cotisation_id,
            reference_paiement=tx.kopar_token,
            mode_paiement=tx.service or "kopar",
        )
        if not c:
            return
        adhesion = await self.adhesions.get_by_id(c.adhesion_id)
        if (
            adhesion
            and self.settings.mail_enabled
            and adhesion.email
            and background_tasks is not None
        ):
            try:
                subject, text, html = build_cotisation_paiement_confirme(
                    adhesion=adhesion,
                    base_url=self.settings.public_base_url or "",
                    annee=c.annee,
                    mois=c.mois,
                    montant=c.montant,
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
