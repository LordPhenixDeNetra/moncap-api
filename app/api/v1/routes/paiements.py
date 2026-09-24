from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_roles
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.enums import AdhesionStatus
from app.models.paiements import (
    CotisationStatut,
    ParametrePaiementCode,
    StatutTransactionKopar,
    TypeTransactionKopar,
    PeriodePaiement,
)
from app.models.user import User
from app.repositories.users import UserRepository
from app.repositories.adhesions import AdhesionRepository
from app.repositories.paiements import CotisationMensuelleRepository, TransactionKoparRepository
from app.schemas.paiements import (
    AdherentEtatCotisationFlatOut,
    AdherentEtatCotisationResponse,
    CotisationDetailListResponse,
    CotisationDetailOut,
    CotisationListResponse,
    CotisationMensuelleOut,
    CotisationStatut as PydanticCotisationStatut,
    InitPaiementAdhesionPublicRequest,
    InitPaiementResponse,
    MoisCotisationLabelOut,
    ParametrePaiementCreate,
    ParametrePaiementOut,
    ParametrePaiementUpdate,
    ParametresPaiementListResponse,
    PaiementManuelPeriodeRequest,
    PaiementManuelRequest,
    ProchainPaiementPeriodeOut,
    ProchainPaiementSuggestionResponse,
    TransactionKoparListResponse,
    TransactionKoparOut,
    AdherentEtatCotisationOut,
)
from app.services.kopar import KoparError
from app.services.paiement_orchestrator import PaiementOrchestratorService
from app.services.paiements import CotisationsService, ParametresPaiementService
from app.services.qr_code import QRCodeStorageService


public_router = APIRouter(prefix="/paiements", tags=["paiements"])
protected_router = APIRouter(prefix="/paiements", tags=["paiements"])
adherent_router = APIRouter(prefix="/mon-compte", tags=["paiements", "adherent"])
admin_router = APIRouter(prefix="/admin", tags=["paiements", "admin"])


def _calculer_paiement_adhesion_confirme_legacy(adhesion: Any) -> bool:
    """Calcule flag paiement adhesion avec SEULEMENT les infos de la ligne adhesion.
    Utilisé comme fallback rapide quand on n'a pas de DB session sous la main.
    Voir aussi _calculer_paiement_adhesion_confirme_async() pour la version DYNAMIQUE
    qui inclut la somme des transactions Kopar SUCCESS en base (source de vérité
    pour les paiements initiaux / manuels anciens où paiement_confirme n'a pas
    été mis à jour en back-office)."""
    flag_bd = bool(getattr(adhesion, "paiement_confirme", False))
    has_ref = (
        getattr(adhesion, "reference_paiement", None) is not None
        and len(str(getattr(adhesion, "reference_paiement", "") or "").strip()) > 0
    )
    montant_legacy_ok = (
        getattr(adhesion, "montant_adhesion_paye", None) is not None
        and getattr(adhesion, "montant_adhesion_paye", 0) >= (getattr(adhesion, "montant_adhesion", None) or 0)
    )
    date_legacy_ok = getattr(adhesion, "date_paiement_adhesion", None) is not None
    return bool(flag_bd or has_ref or montant_legacy_ok or date_legacy_ok)


async def _calculer_paiement_adhesion_confirme(
    adhesion: Any, db: AsyncSession, montant_ref_adhesion_initiale: int | None = None
) -> bool:
    """Calcule DYNAMIQUEMENT paiementAdhesionConfirme (source de vérité = TRANSACTIONS KOPAR).
    Ordre priorité :
      1. (Colonne SQL) adhesion.paiement_confirme = True → OUI
      2. (Colonne SQL) adhesion.reference_paiement non vide → OUI
      3. (SUM DB) Somme montant transactions_kopar.statut=success + type=adhesion + adhesion_id=?
         >= (montant_ref_adhesion_initiale DEPUIS parametres_paiement DB JAMAIS 25000 hardcodé) → OUI
      4. Fallback legacy → OUI
    """
    legacy = _calculer_paiement_adhesion_confirme_legacy(adhesion)
    if legacy:
        return True
    aid = getattr(adhesion, "id", None)
    if aid is None:
        return False
    tx_repo = TransactionKoparRepository(db)
    somme = 0
    try:
        somme = await tx_repo.sommer_montants(
            statut=StatutTransactionKopar.success,
            type_transaction=TypeTransactionKopar.adhesion,
            adhesion_id=uuid.UUID(str(aid)),
        )
    except Exception:
        somme = 0
    if somme <= 0:
        return False
    if montant_ref_adhesion_initiale is None or montant_ref_adhesion_initiale <= 0:
        try:
            params_svc = ParametresPaiementService(db)
            montant_ref_adhesion_initiale = await params_svc.get_montant(
                ParametrePaiementCode.adhesion_initiale, date.today()
            )
        except Exception:
            fallback_col = getattr(adhesion, "montant_adhesion", None) or 0
            montant_ref_adhesion_initiale = fallback_col if fallback_col > 0 else 1
    return int(somme) >= int(montant_ref_adhesion_initiale)


# =========================================================================
# ENDPOINT PUBLIC RACCOURCI QR DIRECT (scanner caméra → page Kopar, pas formulaire MONCAP)
# =========================================================================

def _statut_est_payee(cotisation: Any) -> bool:
    s = getattr(cotisation, "statut", None)
    return (
        s == CotisationStatut.payee
        or (hasattr(s, "value") and s.value == "payee")
        or str(s) == "payee"
    )


def _build_frontend_payer_cotisation_redirect(
    settings: Any, *, adh: uuid.UUID | str, **query_extra: Any
) -> str:
    base_front = (getattr(settings, "public_base_url", None) or "").rstrip("/")
    if not base_front:
        base_front = "https://moncap.innovamind.tech"
    query_parts = [f"adh={str(adh)}"]
    for k, v in query_extra.items():
        if v is None:
            continue
        from urllib.parse import quote as _url_quote
        query_parts.append(f"{k}={_url_quote(str(v))}")
    return f"{base_front}/payer-cotisation?{'&'.join(query_parts)}"


@public_router.get(
    "/cotisation/qr-paiement-direct",
    summary="(Public GET) QR Permanent → redirect 302 VERS LA PAGE FRONTEND `/payer-cotisation` (flux multi-périodes M/T/S/A géré côté front)",
    description="Endpoint appelé PAR LE SCANNER CAMÉRA iOS/Android quand un adhérent·e scanne son QR permanent. "
    "URL courte GET : ?adh=UUID_ADHESION. "
    "Renvoie systématiquement un HTTP 302 FOUND : "
    "(a) adhésion introuvable → /payer-cotisation?adh=UUID&erreur=introuvable ; "
    "(b) adhésion pas encore validée → /payer-cotisation?adh=UUID&erreur=adhesion-en-attente ; "
    "(c) frais adhésion 25.000 non réglés → /payer-cotisation?adh=UUID&erreur=adhesion-impayee ; "
    "(d) CAS HEUREUX (défaut multi-périodes) : NE PLUS initier Kopar ici → redirige VERS LA PAGE FRONTEND "
    "/payer-cotisation?adh=UUID qui affiche les 4 cartes M/T/S/A et gère Kopar elle-même via "
    "`POST /cotisation/initier-public-par-adhesion?periodeMois=1|3|6|12`. Les query params optionnels "
    "`mois`/`annee` (héritage QR ancien) sont IGNORÉS.",
    status_code=302,
    response_class=RedirectResponse,
)
async def qr_paiement_direct_cotisation(
    adh: uuid.UUID = Query(..., alias="adh", description="UUID adhésion (issu QR permanent)"),
    mois: int | str | None = Query(None, alias="mois", description="[IGNORÉ — héritage] mois entier 1-12 ou 'auto'"),
    annee: int | str | None = Query(None, alias="annee", description="[IGNORÉ — héritage] année entier ou 'auto'"),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    adhesion = await AdhesionRepository(db).get_by_id(adh)
    if adhesion is None:
        url = _build_frontend_payer_cotisation_redirect(settings, adh=adh, erreur="introuvable")
        return RedirectResponse(url=url, status_code=302)
    adhesion_validee = (
        getattr(adhesion, "statut", None) == AdhesionStatus.validee
        or (hasattr(getattr(adhesion, "statut", None), "value") and adhesion.statut.value == "validee")
        or str(getattr(adhesion, "statut", "")) == "validee"
    )
    if not adhesion_validee:
        url = _build_frontend_payer_cotisation_redirect(settings, adh=adh, erreur="adhesion-en-attente")
        return RedirectResponse(url=url, status_code=302)
    paiement_adhesion_confirme = await _calculer_paiement_adhesion_confirme(adhesion, db)
    if not paiement_adhesion_confirme:
        url = _build_frontend_payer_cotisation_redirect(settings, adh=adh, erreur="adhesion-impayee")
        return RedirectResponse(url=url, status_code=302)

    # ————————————————————————————————————————————————————
    #    NOUVEAU flux multi-périodes (consigne 2026-09-23) :
    #    On laisse le FRONTEND (/payer-cotisation) gérer :
    #      - affichage des 4 cartes M/T/S/A
    #      - choix période par l'adhérent·e
    #      - appel à POST /cotisation/initier-public-par-adhesion?periodeMois=...
    #        pour initier Kopar (1 transaction = N mois selon la période)
    # ————————————————————————————————————————————————————
    from urllib.parse import urlencode
    query = urlencode({"adh": str(adhesion.id)})
    base_front = (getattr(settings, "public_base_url", None) or "").rstrip("/") or "https://moncap.innovamind.tech"
    frontend_url = f"{base_front}/payer-cotisation?{query}"
    return RedirectResponse(url=frontend_url, status_code=302)


# =========================================================================
# ENDPOINTS PUBLICS (Webhook Kopar + infos paiement adhérent depuis QR)
# =========================================================================

@public_router.post(
    "/webhook/kopar",
    summary="Webhook Kopar Pay (IPN)",
    description="Endpoint appelé par Kopar Pay lors d'un changement de statut de transaction. Vérifie la signature HMAC-SHA256 avant traitement.",
    status_code=200,
)
async def kopar_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_kopar_signature: str = Header("", alias="X-KOPAR-SIGNATURE"),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    raw_body = (await request.body()).decode("utf-8")
    try:
        import json as _json
        json_body = _json_body = _json.loads(raw_body) if raw_body else {}
    except Exception:
        json_body = {}
    orchestrator = PaiementOrchestratorService(db)
    result = await orchestrator.processer_webhook_kopar(
        raw_body=raw_body,
        signature=x_kopar_signature,
        json_body=json_body,
        background_tasks=background_tasks,
    )
    await db.commit()
    if not result.ok:
        return {"ok": False, "code": result.code, "message": result.message}
    return {"ok": True, "code": "OK", "action": result.action}


@public_router.get(
    "/cotisation/etat",
    summary="État cotisation pour un adhérent (accessible par QR)",
    description="Point d'entrée public appelé par la page web atteinte après scan du QR. Retourne infos adhérent + cotisation du mois + montants (format FLAT conforme contrat frontend).",
    response_model=AdherentEtatCotisationFlatOut,
)
async def etat_cotisation_publique(
    adh: uuid.UUID = Query(..., alias="adh", description="UUID de l'adhésion"),
    db: AsyncSession = Depends(get_db),
):
    adhesion = await AdhesionRepository(db).get_by_id(adh)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    adhesion_est_validee = (
        getattr(adhesion, "statut", None) == AdhesionStatus.validee
        or (hasattr(adhesion.statut, "value") and adhesion.statut.value == "validee")
        or str(getattr(adhesion, "statut", "")) == "validee"
    )
    paiement_adhesion_confirme = await _calculer_paiement_adhesion_confirme(adhesion, db)
    qr = QRCodeStorageService()
    _, qr_abs_url = qr.generer_qr_adherent(adhesion.id)
    cotisation_courante: Any = None
    historique: list = []
    montant_annuel_paye = 0
    mois_payes = 0
    montant_du = 0
    premiere_cotisation_annee: int | None = None
    premiere_cotisation_mois: int | None = None
    est_premier_mois_offert = False
    if adhesion_est_validee:
        cotisations_service = CotisationsService(db)
        params_svc = ParametresPaiementService(db)
        date_validation_d: date | None = None
        v_dir = getattr(adhesion, "validation_directoire_at", None)
        if v_dir is not None:
            try:
                date_validation_d = v_dir.date() if hasattr(v_dir, "date") else date.fromisoformat(str(v_dir)[:10])
            except Exception:
                date_validation_d = None
        if date_validation_d is None:
            v_acc = getattr(adhesion, "validation_accueil_at", None)
            if v_acc is not None:
                try:
                    date_validation_d = v_acc.date() if hasattr(v_acc, "date") else date.fromisoformat(str(v_acc)[:10])
                except Exception:
                    date_validation_d = None
        if date_validation_d is None:
            c_at = getattr(adhesion, "created_at", None)
            if c_at is not None:
                try:
                    date_validation_d = c_at.date() if hasattr(c_at, "date") else date.fromisoformat(str(c_at)[:10])
                except Exception:
                    date_validation_d = date.today()
            else:
                date_validation_d = date.today()
        premiere_cotisation_annee, premiere_cotisation_mois = await params_svc.determiner_premier_mois_cotisation(date_validation_d)
        today = date.today()
        est_premier_mois_offert = (premiere_cotisation_annee, premiere_cotisation_mois) > (today.year, today.month)
        cotisation_courante = await cotisations_service.get_cotisation_courante(adhesion.id)
        if cotisation_courante is None and not est_premier_mois_offert:
            try:
                await cotisations_service.generer_pour_adherent_suite_validation(adhesion.id, date_validation_d)
                await db.commit()
                cotisation_courante = await cotisations_service.get_cotisation_courante(adhesion.id)
            except Exception:
                await db.rollback()
                cotisation_courante = None
        if cotisation_courante is None and est_premier_mois_offert:
            try:
                cotisation_courante = await cotisations_service.creer_cotisation(
                    adhesion.id, premiere_cotisation_annee, premiere_cotisation_mois
                )
                await db.commit()
            except Exception:
                await db.rollback()
                cotisation_courante = None
        try:
            montant_reference = await params_svc.get_montant(
                ParametrePaiementCode.cotisation_mensuelle, date.today()
            )
            if montant_reference and montant_reference > 0:
                if cotisation_courante is not None and (
                    getattr(cotisation_courante, "montant", None) is None
                    or getattr(cotisation_courante, "montant", 0) <= 0
                    or abs((getattr(cotisation_courante, "montant", 0) or 0) - montant_reference) > 1
                ):
                    cotisation_courante.montant = montant_reference
        except Exception:
            if cotisation_courante is not None and (getattr(cotisation_courante, "montant", None) is None or getattr(cotisation_courante, "montant", 0) <= 0):
                cotisation_courante.montant = 5
        historique = await cotisations_service.historique_adherent(adhesion.id, 24) or []
        annee_courante = date.today().year
        def _statut_egal_payee(c: Any) -> bool:
            s = getattr(c, "statut", None)
            return s == CotisationStatut.payee or (hasattr(s, "value") and s.value == "payee") or str(s) == "payee"
        montant_annuel_paye = sum(
            (getattr(c, "montant", 0) or 0)
            for c in historique
            if getattr(c, "annee", 0) == annee_courante and _statut_egal_payee(c)
        )
        mois_payes = sum(
            1 for c in historique if getattr(c, "annee", 0) == annee_courante and _statut_egal_payee(c)
        )
        montant_du = 0
        if est_premier_mois_offert:
            montant_du = 0
        elif cotisation_courante is not None:
            cc_montant = getattr(cotisation_courante, "montant", None) or 0
            if not _statut_egal_payee(cotisation_courante):
                montant_du = cc_montant or 0
    def _valeur_statut(s: Any) -> Any:
        v = s.value if hasattr(s, "value") else s
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped == "en_attent":
                return "en_attente"
            return v_stripped
        return v
    cotisation_courante_out = None
    if cotisation_courante is not None:
        cotisation_courante_out = {
            "id": str(getattr(cotisation_courante, "id", "") or ""),
            "adhesionId": str(getattr(cotisation_courante, "adhesion_id", "") or ""),
            "annee": getattr(cotisation_courante, "annee", None),
            "mois": getattr(cotisation_courante, "mois", None),
            "montant": getattr(cotisation_courante, "montant", 0) or 0,
            "devise": getattr(cotisation_courante, "devise", "XOF") or "XOF",
            "statut": _valeur_statut(getattr(cotisation_courante, "statut", None)),
            "paiementDate": getattr(cotisation_courante, "paiement_date", None),
            "modePaiement": getattr(cotisation_courante, "mode_paiement", None),
            "referencePaiement": getattr(cotisation_courante, "reference_paiement", None),
            "paiementManuel": bool(getattr(cotisation_courante, "paiement_manuel", False)),
        }
    historique_24_mois_out = [
        {
            "id": str(getattr(c, "id", "") or ""),
            "annee": getattr(c, "annee", None),
            "mois": getattr(c, "mois", None),
            "montant": getattr(c, "montant", 0) or 0,
            "statut": _valeur_statut(getattr(c, "statut", None)),
            "paiementDate": getattr(c, "paiement_date", None),
        }
        for c in historique or []
    ]
    return {
        "adhesionId": adhesion.id,
        "adhesionEstValidee": bool(adhesion_est_validee),
        "paiementAdhesionConfirme": bool(paiement_adhesion_confirme),
        "nom": getattr(adhesion, "nom", None),
        "prenom": getattr(adhesion, "prenom", None),
        "email": getattr(adhesion, "email", None),
        "telephone": getattr(adhesion, "tel_mobile", None),
        "commissariat": getattr(adhesion, "commissariat", None),
        "qrUrl": qr_abs_url,
        "montantDu": int(montant_du or 0),
        "montantAnnuelPaye": int(montant_annuel_paye or 0),
        "moisPayesAnnee": int(mois_payes or 0),
        "cotisationCourante": cotisation_courante_out,
        "historique24Mois": historique_24_mois_out,
        "premiereCotisationAnnee": premiere_cotisation_annee,
        "premiereCotisationMois": premiere_cotisation_mois,
        "estPremierMoisOffert": bool(est_premier_mois_offert),
    }


@public_router.post(
    "/cotisation/{cotisation_id}/initier-public",
    response_model=InitPaiementResponse,
    summary="(Public) Initier paiement Kopar d'une cotisation mensuelle (scan QR sans JWT)",
    description="Dédié au parcours scan QR Code permanent. Sans JWT, vérification par email. L'adhérent·e fournit l'email lié à son adhésion pour confirmer son identité. Paramètre `periodeMois` pour payer 1/3/6/12 mois d'un coup (commence à la cotisation fournie).",
)
async def initier_paiement_cotisation_public(
    cotisation_id: uuid.UUID,
    body: InitPaiementAdhesionPublicRequest = Body(...),
    service: str | None = Query(None, description="Service de paiement (wave_checkout, orange_money_sn, kopar_services_cross...)"),
    periode_mois: int = Query(1, ge=1, le=12, alias="periodeMois", description="Nombre de mois consécutifs à payer (1/3/6/12)"),
    db: AsyncSession = Depends(get_db),
):
    cot_repo = CotisationMensuelleRepository(db)
    c = await cot_repo.get_by_id(cotisation_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cotisation introuvable")
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(c.adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhérent introuvable")
    if adhesion.statut != AdhesionStatus.validee:
        raise HTTPException(status_code=409, detail="Adhésion non validée")
    email_saisi = (body.email or "").strip().lower()
    email_stocke = (adhesion.email or "").strip().lower()
    if not email_saisi or email_stocke != email_saisi:
        raise HTTPException(
            status_code=403,
            detail="L'email fourni ne correspond pas à cette adhésion",
        )
    try:
        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.cotisation_mensuelle, date.today()
        )
        if montant_reference and montant_reference > 0:
            if c.montant is None or abs(c.montant - montant_reference) > 1:
                c.montant = montant_reference
    except Exception:
        if c.montant is None or c.montant <= 0:
            c.montant = 5
    orchestrator = PaiementOrchestratorService(db)
    try:
        periode = PeriodePaiement.normaliser(periode_mois)
        if periode == 1:
            initie = await orchestrator.initier_paiement_cotisation(
                cotisation_id, service=service, force=False
            )
        else:
            initie = await orchestrator.initier_paiement_cotisation_periode(
                adhesion_id=adhesion.id,
                premiere_annee=int(c.annee),
                premier_mois=int(c.mois),
                periode_mois=periode,
                service=service,
            )
    except KoparError as e:
        detail: dict = {"code": "KOPAR_ERROR", "message": e.message}
        if e.kopar_error_code:
            detail["koparErrorCode"] = e.kopar_error_code
            mapped_prefix = {
                "NO_AUTH": "KOPAR_PSP_NO_AUTH",
                "INVALID_MERCHANT": "KOPAR_PSP_INVALID_MERCHANT",
                "INVALID_SERVICE": "KOPAR_PSP_INVALID_SERVICE",
                "INVALID_AMOUNT": "KOPAR_PSP_INVALID_AMOUNT",
                "DUPLICATE_ORDER": "KOPAR_PSP_DUPLICATE_ORDER",
            }.get(str(e.kopar_error_code).upper())
            if mapped_prefix:
                detail["code"] = mapped_prefix
        if e.status_code in (401, 403):
            http_status = 502
        elif 500 <= e.status_code <= 501 or e.status_code >= 505:
            http_status = 502
        else:
            http_status = e.status_code
        if e.details is not None:
            detail["detailsBrutsKopar"] = e.details
            detail["details"] = e.details
        raise HTTPException(status_code=http_status, detail=detail)
    await db.commit()
    return {
        "koparToken": initie.token,
        "paymentUrl": initie.payment_url,
        "qrCode": initie.qr_code,
        "montant": initie.montant,
        "devise": initie.devise,
    }


@public_router.post(
    "/adhesion/{adhesion_id}/cotisation-du-mois/initier-public",
    response_model=InitPaiementResponse,
    summary="(Public) Payer la cotisation DU MOIS SANS QR Code — juste via UUID adhésion + email",
    description="Alternative au scan QR : adhérent·e fournit son UUID adhésion (lien reçu par email ou tapé) + son email. Backend récupère (ou crée) la cotisation du mois en cours et initie le paiement Kopar. Sans JWT, vérification par email. Paramètre `periodeMois` pour payer 1/3/6/12 mois.",
)
async def initier_paiement_cotisation_du_mois_public_par_adhesion(
    adhesion_id: uuid.UUID,
    body: InitPaiementAdhesionPublicRequest = Body(...),
    service: str | None = Query(None, description="Service de paiement (wave_checkout, orange_money_sn, kopar_services_cross...)"),
    periode_mois: int = Query(1, ge=1, le=12, alias="periodeMois", description="Nombre de mois consécutifs à payer (1/3/6/12)"),
    db: AsyncSession = Depends(get_db),
):
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    if adhesion.statut != AdhesionStatus.validee:
        raise HTTPException(status_code=409, detail=f"Adhésion non validée (statut actuel: {adhesion.statut})")
    email_saisi = (body.email or "").strip().lower()
    email_stocke = (adhesion.email or "").strip().lower()
    if not email_saisi or email_stocke != email_saisi:
        raise HTTPException(status_code=403, detail="L'email fourni ne correspond pas à cette adhésion")
    paiement_adhesion_confirme = await _calculer_paiement_adhesion_confirme(adhesion, db)
    if not paiement_adhesion_confirme:
        raise HTTPException(
            status_code=409,
            detail="Paiement adhésion initiale non confirmé. Veuillez d'abord payer les frais d'adhésion avant de payer une cotisation mensuelle."
        )
    cotisations_service = CotisationsService(db)
    cc = await cotisations_service.get_cotisation_courante(adhesion.id)
    if cc is None:
        today = date.today()
        cc = await cotisations_service.creer_cotisation(adhesion.id, today.year, today.month)
        await db.commit()
    try:
        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.cotisation_mensuelle, date.today()
        )
        if montant_reference and montant_reference > 0:
            if (
                cc.montant is None
                or cc.montant <= 0
                or abs(cc.montant - montant_reference) > 1
            ):
                cc.montant = montant_reference
    except Exception:
        if cc.montant is None or cc.montant <= 0:
            cc.montant = 5
    orchestrator = PaiementOrchestratorService(db)
    try:
        periode = PeriodePaiement.normaliser(periode_mois)
        if periode == 1:
            initie = await orchestrator.initier_paiement_cotisation(
                cc.id, service=service, force=False
            )
        else:
            initie = await orchestrator.initier_paiement_cotisation_periode(
                cc.id,
                periode_mois=periode,
                force=False,
                service=service,
            )
    except KoparError as e:
        detail: dict = {"code": "KOPAR_ERROR", "message": e.message}
        if e.details is not None:
            detail["detailsBrutsKopar"] = e.details
            detail["details"] = e.details
        raise HTTPException(status_code=e.status_code, detail=detail)
    await db.commit()
    return {
        "koparToken": initie.token,
        "paymentUrl": initie.payment_url,
        "qrCode": initie.qr_code,
        "montant": initie.montant,
        "devise": initie.devise,
    }


@public_router.post(
    "/cotisation/initier-public-par-adhesion",
    response_model=InitPaiementResponse,
    summary="(Public — alias court) Payer la cotisation du mois sans QR : ?adh=<UUID> + email",
    description="Alias plus court du endpoint /adhesion/{adhesion_id}/cotisation-du-mois/initier-public. Utile pour les navigateurs quand l'adhérent·e tape l'URL à la main ou clique un lien simple dans son email. Supporte `periodeMois`.",
)
async def initier_paiement_cotisation_public_par_adhesion_query(
    adh: uuid.UUID = Query(..., alias="adh", description="UUID de l'adhésion (même paramètre que /cotisation/etat)"),
    body: InitPaiementAdhesionPublicRequest = Body(...),
    service: str | None = Query(None),
    periode_mois: int = Query(1, ge=1, le=12, alias="periodeMois", description="Nombre de mois consécutifs à payer (1/3/6/12)"),
    db: AsyncSession = Depends(get_db),
):
    return await initier_paiement_cotisation_du_mois_public_par_adhesion(
        adhesion_id=adh, body=body, service=service, periode_mois=periode_mois, db=db
    )


@public_router.get(
    "/parametres-public",
    response_model=ParametresPaiementListResponse,
    summary="(Public) Lister les paramètres de paiement actifs (tarifs + règle première cotisation)",
    description="Endpoint public pour le frontend : charge les tarifs adhésion + cotisation mensuelle + règle de première cotisation DÈS LE FORMULAIRE /adhesion, pour que l'adhérent·e voit immédiatement le montant exact facturé et qu'il n'y ait pas de décalage entre formulaire et paiement Kopar.",
)
async def parametres_paiement_publics(
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    svc = ParametresPaiementService(db)
    items: list = []
    for code in (
        ParametrePaiementCode.adhesion_initiale,
        ParametrePaiementCode.cotisation_mensuelle,
        ParametrePaiementCode.regle_date_premiere_cotisation,
    ):
        p = await svc.repo.get_active_for_code_at(code, today)
        if p is not None:
            items.append(p)
    data: list[ParametrePaiementOut] = [
        ParametrePaiementOut.model_validate(p) for p in items
    ]
    return {"data": data, "count": len(data)}


@public_router.get(
    "/adhesion/{adhesion_id}/cotisation/prochaine-suggestion",
    response_model=ProchainPaiementSuggestionResponse,
    summary="(Public) Suggestions de paiement multi-périodes pour une adhésion (par email)",
)
async def suggestion_cotisation_public_par_adhesion_id(
    adhesion_id: uuid.UUID,
    email: str = Query(..., description="Email de l'adhérent·e (vérification)", alias="email"),
    db: AsyncSession = Depends(get_db),
):
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    email_saisi = (email or "").strip().lower()
    email_stocke = (adhesion.email or "").strip().lower()
    if not email_saisi or email_stocke != email_saisi:
        raise HTTPException(status_code=403, detail="L'email fourni ne correspond pas à cette adhésion")
    return await _build_suggestion_periode(adhesion, db)


@public_router.get(
    "/cotisation/prochaine-suggestion",
    response_model=ProchainPaiementSuggestionResponse,
    summary="(Public — alias court) Suggestions de paiement multi-périodes : ?adh=<UUID>&email=<email>",
)
async def suggestion_cotisation_public_query(
    adh: uuid.UUID = Query(..., alias="adh", description="UUID de l'adhésion"),
    email: str = Query(..., alias="email", description="Email de l'adhérent·e (vérification)"),
    db: AsyncSession = Depends(get_db),
):
    return await suggestion_cotisation_public_par_adhesion_id(adhesion_id=adh, email=email, db=db)


@public_router.post(
    "/adhesion/{adhesion_id}/initier-public",
    response_model=InitPaiementResponse,
    summary="(Public) Initier le paiement Kopar des frais d'adhésion (sans JWT, après soumission du formulaire /adhesion)",
    description="Endpoint public dédié au parcours 'Nouvelle adhésion → Paiement immédiat'. L'utilisateur n'a pas encore de compte JWT. Vérification par email.",
)
async def initier_paiement_adhesion_public(
    adhesion_id: uuid.UUID,
    body: InitPaiementAdhesionPublicRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")

    email_saisi = (body.email or "").strip().lower()
    email_stocke = (adhesion.email or "").strip().lower()
    if not email_saisi or email_stocke != email_saisi:
        raise HTTPException(
            status_code=403,
            detail="L'email fourni ne correspond pas à cette adhésion",
        )

    if adhesion.montant_adhesion is None or adhesion.montant_adhesion <= 0:
        adhesion.montant_adhesion = 25000

    try:
        from app.services.paiements import ParametresPaiementService
        from app.models.paiements import ParametrePaiementCode
        from datetime import date

        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.adhesion_initiale, date.today()
        )
        if montant_reference and montant_reference > 0:
            if (
                adhesion.montant_adhesion is None
                or abs(adhesion.montant_adhesion - montant_reference) > 1
            ):
                adhesion.montant_adhesion = montant_reference
            montant_kopar = montant_reference
        else:
            montant_kopar = adhesion.montant_adhesion or 25000
    except Exception:
        montant_kopar = adhesion.montant_adhesion or 25000

    orchestrator = PaiementOrchestratorService(db)
    try:
        initie = await orchestrator.initier_paiement_adhesion(
            adhesion_id,
            service=body.service_paiement,
            force=False,
            override_prenom=body.prenom,
            override_nom=body.nom,
            override_telephone=body.telephone,
            override_email=body.email,
            override_cni=body.cni,
            override_date_naissance=body.date_naissance,
            override_lieu_naissance=body.lieu_naissance,
        )
    except KoparError as e:
        detail: dict = {"code": "KOPAR_ERROR", "message": e.message}
        if e.details is not None:
            detail["detailsBrutsKopar"] = e.details
            detail["details"] = e.details
        raise HTTPException(status_code=e.status_code, detail=detail)

    await db.commit()
    return {
        "koparToken": initie.token,
        "paymentUrl": initie.payment_url,
        "qrCode": initie.qr_code,
        "montant": initie.montant,
        "devise": initie.devise,
    }


# =========================================================================
# ENDPOINTS PROTÉGÉS : Initier paiement adhésion / cotisation
# =========================================================================

@protected_router.post(
    "/adhesion/{adhesion_id}/initier",
    response_model=InitPaiementResponse,
    summary="Initier le paiement Kopar des frais d'adhésion",
)
async def initier_paiement_adhesion(
    adhesion_id: uuid.UUID,
    service: str | None = Query(None, description="Service de paiement (orange_money_sn, wave_checkout, kopar_services_cross...)"),
    force: bool = Query(False, description="Re-créer une transaction même si déjà payé"),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    if adhesion.montant_adhesion is None or adhesion.montant_adhesion <= 0:
        adhesion.montant_adhesion = 25000
    try:
        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.adhesion_initiale, date.today()
        )
        if montant_reference and montant_reference > 0:
            if (
                adhesion.montant_adhesion is None
                or abs(adhesion.montant_adhesion - montant_reference) > 1
            ):
                adhesion.montant_adhesion = montant_reference
    except Exception:
        pass
    orchestrator = PaiementOrchestratorService(db)
    try:
        initie = await orchestrator.initier_paiement_adhesion(
            adhesion_id, service=service, force=force
        )
    except KoparError as e:
        detail: dict = {"code": "KOPAR_ERROR", "message": e.message}
        if e.details is not None:
            detail["detailsBrutsKopar"] = e.details
            detail["details"] = e.details
        raise HTTPException(status_code=e.status_code, detail=detail)
    await db.commit()
    return {
        "koparToken": initie.token,
        "paymentUrl": initie.payment_url,
        "qrCode": initie.qr_code,
        "montant": initie.montant,
        "devise": initie.devise,
    }


@protected_router.post(
    "/cotisation/{cotisation_id}/initier",
    response_model=InitPaiementResponse,
    summary="Initier le paiement Kopar d'une cotisation mensuelle",
)
async def initier_paiement_cotisation(
    cotisation_id: uuid.UUID,
    service: str | None = Query(None, description="Service de paiement Kopar"),
    force: bool = Query(False),
    periode_mois: int = Query(1, ge=1, le=12, alias="periodeMois", description="Nombre de mois consécutifs à payer (1/3/6/12)"),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    cot_repo = CotisationMensuelleRepository(db)
    c = await cot_repo.get_by_id(cotisation_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Cotisation introuvable")
    try:
        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.cotisation_mensuelle, date.today()
        )
        if montant_reference and montant_reference > 0:
            if c.montant is None or abs(c.montant - montant_reference) > 1:
                c.montant = montant_reference
    except Exception:
        pass
    orchestrator = PaiementOrchestratorService(db)
    try:
        periode = PeriodePaiement.normaliser(periode_mois)
        if periode == 1:
            initie = await orchestrator.initier_paiement_cotisation(
                cotisation_id, service=service, force=force
            )
        else:
            initie = await orchestrator.initier_paiement_cotisation_periode(
                adhesion_id=c.adhesion_id,
                premiere_annee=int(c.annee),
                premier_mois=int(c.mois),
                periode_mois=periode,
                service=service,
            )
    except KoparError as e:
        detail: dict = {"code": "KOPAR_ERROR", "message": e.message}
        if e.details is not None:
            detail["detailsBrutsKopar"] = e.details
            detail["details"] = e.details
        raise HTTPException(status_code=e.status_code, detail=detail)
    await db.commit()
    return {
        "koparToken": initie.token,
        "paymentUrl": initie.payment_url,
        "qrCode": initie.qr_code,
        "montant": initie.montant,
        "devise": initie.devise,
    }


# =========================================================================
# ENDPOINTS ESPACE ADHÉRENT
# =========================================================================

@adherent_router.get(
    "/qr-cotisation",
    summary="Mon QR Code de cotisation (espace adhérent)",
)
async def mon_qr_cotisation(
    regenerate: bool = Query(False, description="Force la régénération du QR"),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get_by_id(principal.user_id)
    if user is None or not getattr(user, "adhesion_id", None):
        raise HTTPException(status_code=404, detail="Aucune adhésion liée à votre compte")
    qr = QRCodeStorageService()
    _, abs_url = qr.generer_qr_adherent(user.adhesion_id, force_regenerate=regenerate)
    lien_paiement = qr.build_paiement_url(user.adhesion_id)
    return {"data": {"qrUrl": abs_url, "lienPaiement": lien_paiement}}


@adherent_router.get(
    "/cotisations",
    response_model=CotisationListResponse,
    summary="Historique de mes cotisations (espace adhérent)",
)
async def mes_cotisations(
    limit: int = Query(24, ge=1, le=60),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get_by_id(principal.user_id)
    if user is None or not getattr(user, "adhesion_id", None):
        return {"data": [], "total": 0}
    service = CotisationsService(db)
    items = await service.historique_adherent(user.adhesion_id, limit)
    return {"data": items, "total": len(items)}


@adherent_router.get(
    "/cotisation-du-mois",
    response_model=AdherentEtatCotisationFlatOut,
    summary="État de ma cotisation du mois en cours",
)
async def ma_cotisation_mois(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get_by_id(principal.user_id)
    if user is None or not getattr(user, "adhesion_id", None):
        raise HTTPException(status_code=404, detail="Aucune adhésion liée à votre compte")
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(user.adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    service = CotisationsService(db)
    params_svc = ParametresPaiementService(db)
    qr = QRCodeStorageService()
    _, qr_abs = qr.generer_qr_adherent(adhesion.id)
    adhesion_est_validee = (
        getattr(adhesion, "statut", None) == AdhesionStatus.validee
        or (hasattr(getattr(adhesion, "statut", None), "value") and adhesion.statut.value == "validee")
        or str(getattr(adhesion, "statut", "")) == "validee"
    )
    paiement_adhesion_confirme = await _calculer_paiement_adhesion_confirme(adhesion, db)
    cc: Any = None
    historique: list = []
    montant_annuel_paye = 0
    mois_payes = 0
    montant_du = 0
    premiere_cotisation_annee: int | None = None
    premiere_cotisation_mois: int | None = None
    est_premier_mois_offert = False
    if adhesion_est_validee:
        date_validation_d: date | None = None
        v_dir = getattr(adhesion, "validation_directoire_at", None)
        if v_dir is not None:
            try:
                date_validation_d = v_dir.date() if hasattr(v_dir, "date") else date.fromisoformat(str(v_dir)[:10])
            except Exception:
                date_validation_d = None
        if date_validation_d is None:
            v_acc = getattr(adhesion, "validation_accueil_at", None)
            if v_acc is not None:
                try:
                    date_validation_d = v_acc.date() if hasattr(v_acc, "date") else date.fromisoformat(str(v_acc)[:10])
                except Exception:
                    date_validation_d = None
        if date_validation_d is None:
            c_at = getattr(adhesion, "created_at", None)
            if c_at is not None:
                try:
                    date_validation_d = c_at.date() if hasattr(c_at, "date") else date.fromisoformat(str(c_at)[:10])
                except Exception:
                    date_validation_d = date.today()
            else:
                date_validation_d = date.today()
        premiere_cotisation_annee, premiere_cotisation_mois = await params_svc.determiner_premier_mois_cotisation(date_validation_d)
        today = date.today()
        est_premier_mois_offert = (premiere_cotisation_annee, premiere_cotisation_mois) > (today.year, today.month)
        cc = await service.get_cotisation_courante(adhesion.id)
        if cc is None and not est_premier_mois_offert:
            try:
                await service.generer_pour_adherent_suite_validation(adhesion.id, date_validation_d)
                await db.commit()
                cc = await service.get_cotisation_courante(adhesion.id)
            except Exception:
                await db.rollback()
                cc = None
        if cc is None and est_premier_mois_offert:
            try:
                cc = await service.creer_cotisation(
                    adhesion.id, premiere_cotisation_annee, premiere_cotisation_mois
                )
                await db.commit()
            except Exception:
                await db.rollback()
                cc = None
        try:
            montant_reference = await params_svc.get_montant(
                ParametrePaiementCode.cotisation_mensuelle, date.today()
            )
            if montant_reference and montant_reference > 0:
                if cc is not None and (
                    getattr(cc, "montant", None) is None
                    or getattr(cc, "montant", 0) <= 0
                    or abs((getattr(cc, "montant", 0) or 0) - montant_reference) > 1
                ):
                    cc.montant = montant_reference
        except Exception:
            if cc is not None and (getattr(cc, "montant", None) is None or getattr(cc, "montant", 0) <= 0):
                cc.montant = 5
        historique = await service.historique_adherent(adhesion.id, 24) or []
        annee = date.today().year
        def _statut_egal_payee(c: Any) -> bool:
            s = getattr(c, "statut", None)
            return s == CotisationStatut.payee or (hasattr(s, "value") and s.value == "payee") or str(s) == "payee"
        montant_annuel_paye = sum(
            (getattr(c, "montant", 0) or 0)
            for c in historique
            if getattr(c, "annee", 0) == annee and _statut_egal_payee(c)
        )
        mois_payes = sum(1 for c in historique if getattr(c, "annee", 0) == annee and _statut_egal_payee(c))
        montant_du = 0
        if est_premier_mois_offert:
            montant_du = 0
        elif cc is not None and not _statut_egal_payee(cc):
            montant_du = getattr(cc, "montant", 0) or 0
    def _valeur_statut(s: Any) -> Any:
        v = s.value if hasattr(s, "value") else s
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped == "en_attent":
                return "en_attente"
            return v_stripped
        return v
    cc_out = None
    if cc is not None:
        cc_out = {
            "id": str(getattr(cc, "id", "") or ""),
            "adhesionId": str(getattr(cc, "adhesion_id", "") or ""),
            "annee": getattr(cc, "annee", None),
            "mois": getattr(cc, "mois", None),
            "montant": getattr(cc, "montant", 0) or 0,
            "devise": getattr(cc, "devise", "XOF") or "XOF",
            "statut": _valeur_statut(getattr(cc, "statut", None)),
            "paiementDate": getattr(cc, "paiement_date", None),
            "modePaiement": getattr(cc, "mode_paiement", None),
            "referencePaiement": getattr(cc, "reference_paiement", None),
            "paiementManuel": bool(getattr(cc, "paiement_manuel", False)),
        }
    historique_out = [
        {
            "id": str(getattr(c, "id", "") or ""),
            "annee": getattr(c, "annee", None),
            "mois": getattr(c, "mois", None),
            "montant": getattr(c, "montant", 0) or 0,
            "statut": _valeur_statut(getattr(c, "statut", None)),
            "paiementDate": getattr(c, "paiement_date", None),
        }
        for c in historique or []
    ]
    return {
        "adhesionId": adhesion.id,
        "adhesionEstValidee": bool(adhesion_est_validee),
        "nom": getattr(adhesion, "nom", None),
        "prenom": getattr(adhesion, "prenom", None),
        "email": getattr(adhesion, "email", None),
        "telephone": getattr(adhesion, "tel_mobile", None),
        "commissariat": getattr(adhesion, "commissariat", None),
        "qrUrl": qr_abs,
        "cotisationCourante": cc_out,
        "montantDu": int(montant_du or 0),
        "montantAnnuelPaye": int(montant_annuel_paye or 0),
        "moisPayesAnnee": int(mois_payes or 0),
        "paiementAdhesionConfirme": bool(paiement_adhesion_confirme),
        "historique24Mois": historique_out,
        "premiereCotisationAnnee": premiere_cotisation_annee,
        "premiereCotisationMois": premiere_cotisation_mois,
        "estPremierMoisOffert": bool(est_premier_mois_offert),
    }


async def _build_suggestion_periode(
    adhesion,
    db: AsyncSession,
) -> ProchainPaiementSuggestionResponse:
    """Construit le jeu de 4 options de paiement (M/T/S/A)."""
    from app.repositories.paiements import CotisationMensuelleRepository
    noms_mois = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    ]
    adhesion_est_validee = (
        getattr(adhesion, "statut", None) == AdhesionStatus.validee
        or (hasattr(getattr(adhesion, "statut", None), "value") and adhesion.statut.value == "validee")
        or str(getattr(adhesion, "statut", "")) == "validee"
    )
    paiement_adhesion_confirme = await _calculer_paiement_adhesion_confirme(adhesion, db)
    cotisations_service = CotisationsService(db)
    cot_repo = CotisationMensuelleRepository(db)
    cc = await cotisations_service.get_cotisation_courante(adhesion.id)
    if cc is None:
        today = date.today()
        cc = await cotisations_service.creer_cotisation(adhesion.id, today.year, today.month)
    try:
        params_svc = ParametresPaiementService(db)
        montant_mensuel = await params_svc.get_montant(
            ParametrePaiementCode.cotisation_mensuelle, date.today()
        ) or int(getattr(cc, "montant", None) or 0)
    except Exception:
        montant_mensuel = int(getattr(cc, "montant", None) or 0)
    if montant_mensuel <= 0:
        montant_mensuel = 5

    premier_an = int(getattr(cc, "annee") or date.today().year)
    premier_mo = int(getattr(cc, "mois") or date.today().month)

    def _gen_periode(start_an, start_mo, nb):
        mois_l = []
        a, m = int(start_an), int(start_mo)
        for _ in range(int(nb)):
            mois_l.append((a, m))
            m += 1
            if m > 12:
                m = 1
                a += 1
        return mois_l

    est_premier_offert = bool(getattr(adhesion, "premier_mois_offert", False))
    premiere_cotisation_an = getattr(adhesion, "premiere_cotisation_annee", None)
    premiere_cotisation_mo = getattr(adhesion, "premiere_cotisation_mois", None)

    async def _est_paye(a, m):
        ligne = await cot_repo.get_for_adherent_mois(adhesion.id, a, m)
        if not ligne:
            return False
        v = str(getattr(ligne, "statut", "") or "")
        return v == "payee" or "paye" in v.lower()

    labels_periode = {1: "Mensuel", 3: "Trimestriel", 6: "Semestriel", 12: "Annuel"}
    options: list[ProchainPaiementPeriodeOut] = []
    for periode in (1, 3, 6, 12):
        liste_mois = _gen_periode(premier_an, premier_mo, periode)
        items_details: list[MoisCotisationLabelOut] = []
        nb_impayes = 0
        nb_offerts = 0
        montant_total = 0
        for (a, m) in liste_mois:
            paye = await _est_paye(a, m)
            est_offert = (
                est_premier_offert
                and (premiere_cotisation_an is not None and premiere_cotisation_mo is not None)
                and int(a) == int(premiere_cotisation_an)
                and int(m) == int(premiere_cotisation_mo)
            )
            st = CotisationStatut.payee if paye else (CotisationStatut.en_attente if not est_offert else CotisationStatut.payee)
            items_details.append(MoisCotisationLabelOut(
                annee=int(a),
                mois=int(m),
                label=f"{noms_mois[m - 1] if 1 <= m <= 12 else str(m)} {a}",
                statut=st,
            ))
            if paye:
                continue
            if est_offert:
                nb_offerts += 1
                continue
            nb_impayes += 1
            montant_total += int(montant_mensuel)

        options.append(ProchainPaiementPeriodeOut(
            periodeMois=int(periode),
            label=labels_periode.get(int(periode), f"{periode} mois"),
            montantTotal=montant_total,
            devise="XOF",
            premierMoisConcerne=items_details[0] if items_details else None,
            listeMois=items_details,
            nbMoisImpayesInclus=int(nb_impayes),
            nbMoisOffertsInclus=int(nb_offerts),
        ))

    return ProchainPaiementSuggestionResponse(
        adhesionId=adhesion.id,
        adhesionEstValidee=bool(adhesion_est_validee),
        paiementAdhesionConfirme=bool(paiement_adhesion_confirme),
        options=options,
    )


@adherent_router.get(
    "/cotisations/prochaine-suggestion",
    response_model=ProchainPaiementSuggestionResponse,
    summary="Mon espace — suggestions de paiement multi-périodes (1/3/6/12 mois)",
)
async def ma_cotisation_suggestions(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get_by_id(principal.user_id)
    if user is None or not getattr(user, "adhesion_id", None):
        raise HTTPException(status_code=404, detail="Aucune adhésion liée à votre compte")
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(user.adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    return await _build_suggestion_periode(adhesion, db)


# =========================================================================
# ENDPOINTS ADMIN : CRUD paramètres paiement, dashboard, paiement manuel
# =========================================================================

@admin_router.get(
    "/parametres-paiement",
    response_model=ParametresPaiementListResponse,
    summary="[Admin] Lister tous les paramètres de paiement",
)
async def admin_list_parametres(
    code: ParametrePaiementCode | str | None = Query(None),
    principal: Principal = Depends(require_roles("admin", "comite_directoire")),
    db: AsyncSession = Depends(get_db),
):
    service = ParametresPaiementService(db)
    if code:
        items = await service.list_for_code(str(code))
    else:
        items = await service.get_all()
    return {"data": items}


@admin_router.post(
    "/parametres-paiement",
    response_model=ParametrePaiementOut,
    summary="[Admin] Créer un nouveau paramètre de paiement (avec transition date_fin_effet)",
)
async def admin_create_parametre(
    payload: ParametrePaiementCreate,
    principal: Principal = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = ParametresPaiementService(db)
    from datetime import timedelta
    from app.models.paiements import ParametrePaiement as PModel
    nouveau = PModel(
        code=str(payload.code),
        libelle=payload.libelle,
        montant_fcfa=payload.montant_fcfa,
        valeur_texte=payload.valeur_texte,
        devise=payload.devise,
        date_effet=payload.date_effet,
        date_fin_effet=payload.date_fin_effet,
    )
    if payload.date_effet and payload.date_effet.day > 1:
        fin_existant = payload.date_effet - timedelta(days=1)
    else:
        fin_existant = payload.date_effet - timedelta(days=1)
    saved = await service.parametres.close_current_and_insert(
        code=str(payload.code),
        nouveau=nouveau,
        date_fin_existant=fin_existant,
    )
    await db.commit()
    await db.refresh(saved)
    return saved


@admin_router.patch(
    "/parametres-paiement/{pid}",
    response_model=ParametrePaiementOut,
    summary="[Admin] Modifier un paramètre existant",
)
async def admin_update_parametre(
    pid: uuid.UUID,
    payload: ParametrePaiementUpdate,
    principal: Principal = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = ParametresPaiementService(db)
    data = payload.model_dump(exclude_unset=True)
    updated = await service.modifier_parametre(pid, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Paramètre introuvable")
    await db.commit()
    await db.refresh(updated)
    return updated


@admin_router.get(
    "/cotisations/dashboard",
    summary="[Admin] Dashboard état cotisations pour un mois donné",
)
async def admin_dashboard_cotisations(
    annee: int = Query(default_factory=lambda: date.today().year),
    mois: int = Query(default_factory=lambda: date.today().month),
    principal: Principal = Depends(require_roles("admin", "comite_directoire", "coordinateur_regional", "coordinateur_commissariat")),
    db: AsyncSession = Depends(get_db),
):
    service = CotisationsService(db)
    rapport = await service.rapport_mois(annee, mois)
    return {
        "data": {
            "annee": rapport.annee,
            "mois": rapport.mois,
            "total": rapport.total,
            "payes": rapport.payes,
            "enAttente": rapport.en_attente,
            "echues": rapport.echues,
            "tauxPaiementPct": round(rapport.payes / rapport.total * 100, 1) if rapport.total else 0,
            "montantTotal": rapport.montant_total,
            "montantPerçu": rapport.montant_percu,
            "montantRestant": rapport.montant_total - rapport.montant_percu,
        }
    }


@admin_router.get(
    "/cotisations",
    response_model=CotisationDetailListResponse,
    summary="[Admin] Lister les cotisations pour un mois (filtrables)",
)
async def admin_list_cotisations(
    annee: int = Query(default_factory=lambda: date.today().year),
    mois: int = Query(default_factory=lambda: date.today().month),
    statut: PydanticCotisationStatut | None = Query(None),
    region_id: uuid.UUID | None = Query(None),
    commissariat: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    principal: Principal = Depends(require_roles("admin", "comite_directoire", "coordinateur_regional", "coordinateur_commissariat")),
    db: AsyncSession = Depends(get_db),
):
    service = CotisationsService(db)
    repo = service.repo
    items = await repo.list_for_mois(
        annee=annee,
        mois=mois,
        statut=(CotisationStatut(statut.value) if statut else None),
        region_id=region_id,
        commissariat=commissariat,
        offset=offset,
        limit=limit,
    )
    total = await repo.count_for_mois(annee, mois)
    payes = await repo.count_for_mois(annee, mois, CotisationStatut.payee)
    impayes = total - payes
    from app.models.adhesion import Adhesion as AdhModel
    detail_items: list[dict] = []
    adhesion_ids = [c.adhesion_id for c in items]
    adh_map: dict[uuid.UUID, Any] = {}
    if adhesion_ids:
        q_adh = select(AdhModel).where(AdhModel.id.in_(adhesion_ids))
        res_adh = await db.execute(q_adh)
        for adh in res_adh.scalars().all():
            adh_map[adh.id] = adh
    for c in items:
        adh = adh_map.get(c.adhesion_id)
        detail_items.append({
            "id": c.id,
            "adhesionId": c.adhesion_id,
            "annee": c.annee,
            "mois": c.mois,
            "montant": c.montant,
            "devise": c.devise,
            "statut": c.statut,
            "paiementDate": c.paiement_date,
            "modePaiement": c.mode_paiement,
            "referencePaiement": c.reference_paiement,
            "paiementManuel": c.paiement_manuel,
            "paiementManuelNote": c.paiement_manuel_note,
            "relanceEnvoyee1": c.relance_envoyee_1,
            "relanceEnvoyee2": c.relance_envoyee_2,
            "createdAt": c.created_at,
            "updatedAt": c.updated_at,
            "adhesionNom": adh.nom if adh else None,
            "adhesionPrenom": adh.prenom if adh else None,
            "adhesionEmail": adh.email if adh else None,
            "adhesionTelMobile": adh.tel_mobile if adh else None,
            "adhesionCommissariat": adh.commissariat if adh else None,
        })
    return {"data": detail_items, "total": total, "payes": payes, "impayes": impayes}


@admin_router.post(
    "/cotisations/{cotisation_id}/paiement-manuel",
    response_model=CotisationMensuelleOut,
    summary="[Admin] Enregistrer un paiement manuel d'une cotisation",
)
async def admin_paiement_manuel_cotisation(
    cotisation_id: uuid.UUID,
    payload: PaiementManuelRequest,
    principal: Principal = Depends(require_roles("admin", "comite_directoire", "coordinateur_regional")),
    db: AsyncSession = Depends(get_db),
):
    service = CotisationsService(db)
    c = await service.paiement_manuel(
        cotisation_id=cotisation_id,
        user_id=principal.user_id,
        note=payload.note,
        reference_paiement=payload.reference_paiement,
    )
    await db.commit()
    await db.refresh(c)
    return c


@admin_router.post(
    "/adhesions/{adhesion_id}/cotisations/paiement-manuel-periode",
    response_model=CotisationListResponse,
    summary="[Admin] Enregistrer un paiement manuel sur 1/3/6/12 mois consécutifs",
)
async def admin_paiement_manuel_periode(
    adhesion_id: uuid.UUID,
    payload: PaiementManuelPeriodeRequest,
    annee: int | None = Query(None, description="Année de départ (défaut: aujourd'hui)"),
    mois: int | None = Query(None, description="Mois de départ 1-12 (défaut: aujourd'hui)"),
    principal: Principal = Depends(require_roles("admin", "comite_directoire", "coordinateur_regional")),
    db: AsyncSession = Depends(get_db),
):
    adhesion_repo = AdhesionRepository(db)
    adhesion = await adhesion_repo.get_by_id(adhesion_id)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    today = date.today()
    debut_an = int(annee) if annee else today.year
    debut_mo = int(mois) if mois else today.month
    if not (1 <= debut_mo <= 12):
        raise HTTPException(status_code=400, detail="mois doit être entre 1 et 12")
    periode = PeriodePaiement.normaliser(payload.periode_mois)
    mois_consecutifs = CotisationMensuelleRepository.calculer_mois_consecutifs(
        debut_an, debut_mo, periode
    )
    service = CotisationsService(db)
    cot_repo = CotisationMensuelleRepository(db)
    resultats: list = []
    for (a, m) in mois_consecutifs:
        cc = await cot_repo.get_or_create_for_adherent_mois(adhesion.id, int(a), int(m))
        ligne = await service.paiement_manuel(
            cotisation_id=cc.id,
            user_id=principal.user_id,
            note=payload.note,
            reference_paiement=payload.reference_paiement,
        )
        resultats.append(ligne)
    await db.commit()
    for r in resultats:
        await db.refresh(r)
    return {"data": resultats, "total": len(resultats)}


@admin_router.get(
    "/transactions-kopar",
    response_model=TransactionKoparListResponse,
    summary="[Admin] Historique transactions Kopar Pay",
)
async def admin_list_transactions_kopar(
    adhesion_id: uuid.UUID | None = Query(None),
    type_tx: TypeTransactionKopar | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    principal: Principal = Depends(require_roles("admin", "comite_directoire")),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.paiements import TransactionKoparRepository
    repo = TransactionKoparRepository(db)
    from app.models.paiements import TransactionKopar as TK
    q = select(TK).order_by(desc(TK.created_at)).limit(limit)
    if adhesion_id:
        q = q.where(TK.adhesion_id == adhesion_id)
    if type_tx:
        q = q.where(TK.type_transaction == type_tx)
    res = await db.execute(q)
    items = list(res.scalars().all())
    return {"data": items}


@admin_router.post(
    "/cotisations/generer-mois",
    summary="[Admin] Générer les cotisations pour TOUS les adhérents validés (un mois)",
)
async def admin_generer_mois(
    annee: int = Query(default_factory=lambda: date.today().year),
    mois: int = Query(default_factory=lambda: date.today().month),
    principal: Principal = Depends(require_roles("admin", "comite_directoire")),
    db: AsyncSession = Depends(get_db),
):
    service = CotisationsService(db)
    total, crees = await service.generer_tous_les_du_mois(annee, mois)
    await db.commit()
    return {"data": {"annee": annee, "mois": mois, "adherentsTotal": total, "nouvellesCotisations": crees}}
