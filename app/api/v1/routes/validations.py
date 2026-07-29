from __future__ import annotations

import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles, get_principal
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.enums import AdhesionStatus, AppRole
from app.models.user import User
from app.repositories.adhesions import AdhesionRepository
from app.schemas.admin import (
    AdminUpdateAdhesionRequest,
    AdminUpdateAdhesionResponse,
)
from app.services.adhesion_mail_templates import build_adhesion_status_changed
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

    if before.statut != AdhesionStatus.en_attente:
        raise HTTPException(status_code=400, detail=f"L'adhésion n'est pas en attente de validation (statut actuel: {before.statut})")

    rowcount = await AdhesionRepository(db).update_status_accueil(
        adhesion_id=adhesion_id,
        user_id=principal.id,
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
        user_id=principal.id,
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
