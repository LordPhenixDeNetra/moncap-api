from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Request, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_roles
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.enums import AdhesionStatus
from app.models.paiements import (
    CotisationStatut,
    ParametrePaiementCode,
    TypeTransactionKopar,
)
from app.models.user import User
from app.repositories.users import UserRepository
from app.repositories.adhesions import AdhesionRepository
from app.repositories.paiements import CotisationMensuelleRepository
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
    ParametrePaiementCreate,
    ParametrePaiementOut,
    ParametrePaiementUpdate,
    ParametresPaiementListResponse,
    PaiementManuelRequest,
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


def _calculer_paiement_adhesion_confirme(adhesion: Any) -> bool:
    """Calcule flag 'paiementAdhesionConfirme' de maniere SURE.

    Le modele SQL Adhesion (app/models/adhesion.py:71-73) expose :
      - montant_adhesion: int (montant demandé / figé)
      - paiement_confirme: bool (seule source de vérité officielle)
      - reference_paiement: str | None
    Les champs 'montant_adhesion_paye' et 'date_paiement_adhesion' N'EXISTENT PAS.
    On les garde dans un getattr(, None) safe pour compatibilite retro si un jour ajoutés en migration.
    """
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
    description="Point d'entrée public appelé par la page web atteinte après scan du QR. Retourne infos adhérent + cotisation du mois + montants.",
    response_model=AdherentEtatCotisationResponse,
)
async def etat_cotisation_publique(
    adh: uuid.UUID = Query(..., alias="adh", description="UUID de l'adhésion"),
    db: AsyncSession = Depends(get_db),
):
    adhesion = await AdhesionRepository(db).get_by_id(adh)
    if not adhesion:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    if adhesion.statut != AdhesionStatus.validee:
        raise HTTPException(
            status_code=409,
            detail=f"Adhésion non validée (statut actuel: {adhesion.statut})",
        )
    paiement_adhesion_confirme = _calculer_paiement_adhesion_confirme(adhesion)
    cotisations_service = CotisationsService(db)
    qr = QRCodeStorageService()
    _, qr_abs_url = qr.generer_qr_adherent(adhesion.id)
    cotisation_courante = await cotisations_service.get_cotisation_courante(adhesion.id)
    if cotisation_courante is None:
        today = date.today()
        try:
            cotisation_courante = await cotisations_service.creer_cotisation(
                adhesion.id, today.year, today.month
            )
            await db.commit()
        except Exception:
            await db.rollback()
            cotisation_courante = None
    try:
        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.cotisation_mensuelle, date.today()
        )
        if montant_reference and montant_reference > 0:
            if cotisation_courante is not None and (
                cotisation_courante.montant is None
                or cotisation_courante.montant <= 0
                or abs(cotisation_courante.montant - montant_reference) > 1
            ):
                cotisation_courante.montant = montant_reference
    except Exception:
        if cotisation_courante is not None and (cotisation_courante.montant is None or cotisation_courante.montant <= 0):
            cotisation_courante.montant = 5
    historique = await cotisations_service.historique_adherent(adhesion.id, 24)
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
    if cotisation_courante is not None:
        cc_statut = getattr(cotisation_courante, "statut", None)
        cc_montant = getattr(cotisation_courante, "montant", None) or 0
        if not _statut_egal_payee(cotisation_courante):
            montant_du = cc_montant or 0
    def _valeur_statut(s: Any) -> Any:
        return s.value if hasattr(s, "value") else s
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
        "data": {
            "adhesionId": str(adhesion.id),
            "nom": getattr(adhesion, "nom", None),
            "prenom": getattr(adhesion, "prenom", None),
            "email": getattr(adhesion, "email", None),
            "telephone": getattr(adhesion, "tel_mobile", None),
            "commissariat": getattr(adhesion, "commissariat", None),
            "paiementAdhesionConfirme": bool(paiement_adhesion_confirme),
            "qrUrl": qr_abs_url,
            "montantDu": int(montant_du or 0),
            "montantAnnuelPaye": int(montant_annuel_paye or 0),
            "moisPayesAnnee": int(mois_payes or 0),
            "cotisationCourante": cotisation_courante_out,
            "historique": historique_out,
        }
    }


@public_router.post(
    "/cotisation/{cotisation_id}/initier-public",
    response_model=InitPaiementResponse,
    summary="(Public) Initier paiement Kopar d'une cotisation mensuelle (scan QR sans JWT)",
    description="Dédié au parcours scan QR Code permanent. Sans JWT, vérification par email. L'adhérent·e fournit l'email lié à son adhésion pour confirmer son identité.",
)
async def initier_paiement_cotisation_public(
    cotisation_id: uuid.UUID,
    body: InitPaiementAdhesionPublicRequest = Body(...),
    service: str | None = Query(None, description="Service de paiement (wave_checkout, orange_money_sn, kopar_services_cross...)"),
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
        initie = await orchestrator.initier_paiement_cotisation(
            cotisation_id, service=service, force=False
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
    description="Alternative au scan QR : adhérent·e fournit son UUID adhésion (lien reçu par email ou tapé) + son email. Backend récupère (ou crée) la cotisation du mois en cours et initie le paiement Kopar. Sans JWT, vérification par email.",
)
async def initier_paiement_cotisation_du_mois_public_par_adhesion(
    adhesion_id: uuid.UUID,
    body: InitPaiementAdhesionPublicRequest = Body(...),
    service: str | None = Query(None, description="Service de paiement (wave_checkout, orange_money_sn, kopar_services_cross...)"),
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
    paiement_adhesion_confirme = _calculer_paiement_adhesion_confirme(adhesion)
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
        initie = await orchestrator.initier_paiement_cotisation(
            cc.id, service=service, force=False
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
    description="Alias plus court du endpoint /adhesion/{adhesion_id}/cotisation-du-mois/initier-public. Utile pour les navigateurs quand l'adhérent·e tape l'URL à la main ou clique un lien simple dans son email.",
)
async def initier_paiement_cotisation_public_par_adhesion_query(
    adh: uuid.UUID = Query(..., alias="adh", description="UUID de l'adhésion (même paramètre que /cotisation/etat)"),
    body: InitPaiementAdhesionPublicRequest = Body(...),
    service: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await initier_paiement_cotisation_du_mois_public_par_adhesion(
        adhesion_id=adh, body=body, service=service, db=db
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
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    try:
        from app.repositories.paiements import CotisationMensuelleRepository

        cot_repo = CotisationMensuelleRepository(db)
        c = await cot_repo.get_by_id(cotisation_id)
        if c is not None:
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
        initie = await orchestrator.initier_paiement_cotisation(
            cotisation_id, service=service, force=force
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
    qr = QRCodeStorageService()
    _, qr_abs = qr.generer_qr_adherent(adhesion.id)
    cc = await service.get_cotisation_courante(adhesion.id)
    if cc is None:
        today = date.today()
        try:
            cc = await service.creer_cotisation(adhesion.id, today.year, today.month)
            await db.commit()
        except Exception:
            await db.rollback()
            cc = None
    try:
        params_svc = ParametresPaiementService(db)
        montant_reference = await params_svc.get_montant(
            ParametrePaiementCode.cotisation_mensuelle, date.today()
        )
        if montant_reference and montant_reference > 0:
            if cc is not None and (
                cc.montant is None
                or cc.montant <= 0
                or abs(cc.montant - montant_reference) > 1
            ):
                cc.montant = montant_reference
    except Exception:
        if cc is not None and (cc.montant is None or cc.montant <= 0):
            cc.montant = 5
    historique = await service.historique_adherent(adhesion.id, 24)
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
    if cc is not None and not _statut_egal_payee(cc):
        montant_du = getattr(cc, "montant", 0) or 0
    paiement_adhesion_confirme = _calculer_paiement_adhesion_confirme(adhesion)
    def _valeur_statut(s: Any) -> Any:
        return s.value if hasattr(s, "value") else s
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
        "historique": historique_out,
    }


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
