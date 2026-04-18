from __future__ import annotations

import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.db.session import get_db
from app.models.enums import AdhesionStatus
from app.repositories.adhesions import AdhesionRepository
from app.schemas.admin import AdminAdhesionListResponse, AdminUpdateAdhesionRequest, AdminUpdateAdhesionResponse

router = APIRouter(prefix="/admin", dependencies=[Depends(require_roles("admin"))])


@router.get(
    "/adhesions",
    response_model=AdminAdhesionListResponse,
    summary="Lister les adhésions (Admin)",
    description="Permet aux administrateurs de lister, filtrer et rechercher parmi toutes les demandes d'adhésion. Supporte la pagination.",
)
async def list_adhesions(
    limit: int = 50,
    offset: int = 0,
    status: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    items, total = await AdhesionRepository(db).list_admin(
        limit=limit,
        offset=offset,
        status=status,
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


@router.patch(
    "/adhesions/{adhesion_id}",
    response_model=AdminUpdateAdhesionResponse,
    summary="Mettre à jour le statut d'une adhésion",
    description="Permet de valider ou rejeter une demande d'adhésion. Un motif est obligatoire en cas de rejet.",
)
async def update_adhesion(
    adhesion_id: uuid.UUID,
    payload: AdminUpdateAdhesionRequest,
    db: AsyncSession = Depends(get_db),
):
    if payload.statut == AdhesionStatus.rejetee and not (payload.motif_rejet and payload.motif_rejet.strip()):
        raise HTTPException(status_code=400, detail="Motif requis si rejet")
    rowcount = await AdhesionRepository(db).update_status(
        adhesion_id=adhesion_id, statut=payload.statut, motif_rejet=payload.motif_rejet
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    await db.commit()
    return {"data": {"updated": True}}


@router.get(
    "/adhesions/export.csv",
    summary="Exporter les adhésions en CSV",
    description="Génère un fichier CSV contenant les données des adhésions filtrées. Idéal pour les rapports Excel.",
)
async def export_csv(
    status: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    items, _ = await AdhesionRepository(db).list_admin(
        limit=100000,
        offset=0,
        status=status,
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )

    def _iter():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "nom",
                "prenom",
                "email",
                "tel_mobile",
                "cni",
                "commissariat",
                "statut",
                "created_at",
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for x in items:
            writer.writerow(
                [
                    str(x.id),
                    x.nom,
                    x.prenom,
                    x.email,
                    x.tel_mobile,
                    x.cni,
                    x.commissariat,
                    x.statut.value if hasattr(x.statut, "value") else str(x.statut),
                    x.created_at.isoformat() if x.created_at else "",
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    headers = {"Content-Disposition": 'attachment; filename="adhesions.csv"'}
    return StreamingResponse(_iter(), media_type="text/csv; charset=utf-8", headers=headers)
