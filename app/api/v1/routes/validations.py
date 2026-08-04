from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles, get_principal
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.enums import AdhesionStatus, AppRole
from app.models.user import User
from app.repositories.adhesions import AdhesionRepository
from app.schemas.admin import (
    AdminAdhesionListResponse,
    AdminUpdateAdhesionRequest,
    AdminUpdateAdhesionResponse,
)
from app.schemas.adhesions import AdhesionDetailResponse
from app.services.adhesion_mail_templates import build_adhesion_status_changed
from app.services.adhesions import AdhesionService
from app.services.mail import send_email_best_effort

accueil_router = APIRouter(
    prefix="/accueil",
    dependencies=[Depends(require_roles(AppRole.comite_accueil))]
)

directoire_router = APIRouter(
    prefix="/directoire",
    dependencies=[Depends(require_roles(AppRole.comite_directoire))]
)

rejection_router = APIRouter(
    dependencies=[Depends(require_roles(AppRole.comite_accueil, AppRole.comite_directoire))]
)


_ACCUEIL_STATUTS = {AdhesionStatus.en_attente, AdhesionStatus.complement, AdhesionStatus.rejetee}
_DIRECTOIRE_STATUTS = {AdhesionStatus.validee_accueil, AdhesionStatus.rejetee, AdhesionStatus.validee}


@accueil_router.get(
    "/adhesions",
    response_model=AdminAdhesionListResponse,
    summary="Lister les adhésions (Accueil)",
    description="Retourne les adhésions avec les statuts 'en_attente', 'complement' et 'rejetee'. Filtrable par ?statut=.",
)
async def list_adhesions_accueil(
    limit: int = 50,
    offset: int = 0,
    statut: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if statut is not None and statut not in _ACCUEIL_STATUTS:
        raise HTTPException(
            status_code=403,
            detail=f"Statut non autorisé pour le comité d'accueil. Valeurs acceptées: {[s.value for s in _ACCUEIL_STATUTS]}",
        )
    items, total = await AdhesionRepository(db).list_admin_multi_status(
        limit=limit,
        offset=offset,
        statuts=list(_ACCUEIL_STATUTS) if statut is None else [statut],
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )
    return {
        "data": [
            {
                "id": x.id,
                "nom": x.nom,
                "prenom": x.prenom,
                "email": x.email,
                "cni": x.cni,
                "commissariat": x.commissariat,
                "statut": x.statut,
                "createdAt": x.created_at,
            }
            for x in items
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@accueil_router.get(
    "/adhesions/lookup",
    response_model=AdhesionDetailResponse,
    summary="Récupérer le détail d'une adhésion (Accueil)",
    description="Retourne la fiche complète d'une adhésion. Recherche par id, email, cni ou tel_mobile.",
)
async def lookup_adhesion_accueil(
    id: uuid.UUID | None = None,
    email: str | None = None,
    cni: str | None = None,
    tel_mobile: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    adhesion = await AdhesionService(db).lookup_details(
        adhesion_id=id, email=email, cni=cni, tel_mobile=tel_mobile
    )
    return {"data": adhesion}


@directoire_router.get(
    "/adhesions",
    response_model=AdminAdhesionListResponse,
    summary="Lister les adhésions (Directoire)",
    description="Retourne les adhésions avec les statuts 'validee_accueil', 'rejetee' et 'validee'. Filtrable par ?statut=.",
)
async def list_adhesions_directoire(
    limit: int = 50,
    offset: int = 0,
    statut: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if statut is not None and statut not in _DIRECTOIRE_STATUTS:
        raise HTTPException(
            status_code=403,
            detail=f"Statut non autorisé pour le comité directoire. Valeurs acceptées: {[s.value for s in _DIRECTOIRE_STATUTS]}",
        )
    items, total = await AdhesionRepository(db).list_admin_multi_status(
        limit=limit,
        offset=offset,
        statuts=list(_DIRECTOIRE_STATUTS) if statut is None else [statut],
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )
    return {
        "data": [
            {
                "id": x.id,
                "nom": x.nom,
                "prenom": x.prenom,
                "email": x.email,
                "cni": x.cni,
                "commissariat": x.commissariat,
                "statut": x.statut,
                "createdAt": x.created_at,
            }
            for x in items
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@directoire_router.get(
    "/adhesions/lookup",
    response_model=AdhesionDetailResponse,
    summary="Récupérer le détail d'une adhésion (Directoire)",
    description="Retourne la fiche complète d'une adhésion. Recherche par id, email, cni ou tel_mobile.",
)
async def lookup_adhesion_directoire(
    id: uuid.UUID | None = None,
    email: str | None = None,
    cni: str | None = None,
    tel_mobile: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    adhesion = await AdhesionService(db).lookup_details(
        adhesion_id=id, email=email, cni=cni, tel_mobile=tel_mobile
    )
    return {"data": adhesion}


@accueil_router.patch(
    "/adhesions/{adhesion_id}/valider",
    response_model=AdminUpdateAdhesionResponse,
    summary="Valider une adhésion (Accueil)",
    description="Permet au comité d'accueil de valider la première étape d'une demande d'adhésion.",
)
async def valider_adhesion_accueil(
    adhesion_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: User = Depends(get_principal),
):
    before = await AdhesionRepository(db).get_by_id(adhesion_id)
    if not before:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")

    if before.statut not in {AdhesionStatus.en_attente, AdhesionStatus.complement}:
        raise HTTPException(
            status_code=400,
            detail=f"L'adhésion n'est pas en attente de validation ou en complément (statut actuel: {before.statut})",
        )

    rowcount = await AdhesionRepository(db).update_status_accueil(
        adhesion_id=adhesion_id,
        user_id=principal.user_id,
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")

    await db.commit()
    after = await AdhesionRepository(db).get_by_id(adhesion_id)
    settings = get_settings()
    if settings.mail_enabled and after and after.email:
        subject, text, html = build_adhesion_status_changed(
            adhesion=after, old_status=before.statut, base_url=settings.public_base_url
        )
        background_tasks.add_task(
            send_email_best_effort,
            to=after.email,
            subject=subject,
            text=text,
            html=html,
            settings=settings,
        )
    return {"data": {"updated": True}}


@directoire_router.patch(
    "/adhesions/{adhesion_id}/valider",
    response_model=AdminUpdateAdhesionResponse,
    summary="Valider une adhésion (Directoire)",
    description="Permet au comité directoire de finaliser la validation d'une demande d'adhésion.",
)
async def valider_adhesion_directoire(
    adhesion_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: User = Depends(get_principal),
):
    before = await AdhesionRepository(db).get_by_id(adhesion_id)
    if not before:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")

    if before.statut != AdhesionStatus.validee_accueil:
        raise HTTPException(status_code=400, detail=f"L'adhésion n'a pas été validée par le comité d'accueil (statut actuel: {before.statut})")

    rowcount = await AdhesionRepository(db).update_status_directoire(
        adhesion_id=adhesion_id,
        user_id=principal.user_id,
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")

    await db.commit()
    after = await AdhesionRepository(db).get_by_id(adhesion_id)
    settings = get_settings()
    if settings.mail_enabled and after and after.email:
        subject, text, html = build_adhesion_status_changed(
            adhesion=after, old_status=before.statut, base_url=settings.public_base_url
        )
        background_tasks.add_task(
            send_email_best_effort,
            to=after.email,
            subject=subject,
            text=text,
            html=html,
            settings=settings,
        )
    return {"data": {"updated": True}}


@rejection_router.patch(
    "/adhesions/{adhesion_id}/rejeter",
    response_model=AdminUpdateAdhesionResponse,
    summary="Rejeter une adhésion",
    description="Permet de rejeter une demande d'adhésion. Un motif est obligatoire.",
)
async def rejeter_adhesion(
    adhesion_id: uuid.UUID,
    payload: AdminUpdateAdhesionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if not (payload.motif_rejet and payload.motif_rejet.strip()):
        raise HTTPException(status_code=400, detail="Motif requis si rejet")

    before = await AdhesionRepository(db).get_by_id(adhesion_id)
    if not before:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")

    if before.statut not in [AdhesionStatus.en_attente, AdhesionStatus.validee_accueil]:
        raise HTTPException(status_code=400, detail=f"L'adhésion n'est pas en attente de validation (statut actuel: {before.statut})")

    rowcount = await AdhesionRepository(db).update_status(
        adhesion_id=adhesion_id, statut=AdhesionStatus.rejetee, motif_rejet=payload.motif_rejet
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    await db.commit()
    after = await AdhesionRepository(db).get_by_id(adhesion_id)
    settings = get_settings()
    if settings.mail_enabled and after and after.email:
        subject, text, html = build_adhesion_status_changed(
            adhesion=after, old_status=before.statut, base_url=settings.public_base_url
        )
        background_tasks.add_task(
            send_email_best_effort,
            to=after.email,
            subject=subject,
            text=text,
            html=html,
            settings=settings,
        )
    return {"data": {"updated": True}}
