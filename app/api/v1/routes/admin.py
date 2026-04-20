from __future__ import annotations

import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.db.session import get_db
from app.models.enums import AdhesionStatus
from app.repositories.adhesions import AdhesionRepository
from app.schemas.admin import AdminAdhesionListResponse, AdminUpdateAdhesionRequest, AdminUpdateAdhesionResponse
from app.schemas.adhesions import AdhesionDetailResponse
from app.services.adhesions import AdhesionService

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
    "/adhesions/lookup",
    response_model=AdhesionDetailResponse,
    summary="Récupérer une adhésion (lookup)",
    description="Retourne la fiche complète d'une adhésion en recherchant par id, email, cni ou tel_mobile. Un seul critère doit être fourni.",
)
async def lookup_adhesion(
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
    items = await AdhesionRepository(db).list_admin_export_rows(
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
                "region_domicile_nom",
                "departement_domicile_nom",
                "commune_domicile_nom",
                "region_militantisme_nom",
                "departement_militantisme_nom",
                "commune_militantisme_nom",
                "mode_paiement",
                "montant_adhesion",
                "paiement_confirme",
                "reference_paiement",
                "commissariat",
                "statut",
                "created_at",
            ]
        )
        yield "\ufeff" + buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for x in items:
            writer.writerow(
                [
                    str(x["id"]),
                    x["nom"],
                    x["prenom"],
                    x["email"],
                    x["tel_mobile"],
                    x["cni"],
                    x["region_domicile_nom"],
                    x["departement_domicile_nom"],
                    x["commune_domicile_nom"],
                    x["region_militantisme_nom"],
                    x["departement_militantisme_nom"],
                    x["commune_militantisme_nom"],
                    x["mode_paiement"].value if hasattr(x["mode_paiement"], "value") else str(x["mode_paiement"]),
                    x["montant_adhesion"],
                    x["paiement_confirme"],
                    x["reference_paiement"],
                    x["commissariat"],
                    x["statut"].value if hasattr(x["statut"], "value") else str(x["statut"]),
                    x["created_at"].isoformat() if x["created_at"] else "",
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    headers = {"Content-Disposition": 'attachment; filename="adhesions.csv"'}
    return StreamingResponse(_iter(), media_type="text/csv; charset=utf-8", headers=headers)


@router.get(
    "/adhesions/export.xlsx",
    summary="Exporter les adhésions en Excel",
    description="Génère un fichier Excel (.xlsx) contenant les données des adhésions filtrées, avec un encodage correct pour les caractères spéciaux.",
)
async def export_xlsx(
    status: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        from openpyxl import Workbook
    except ModuleNotFoundError:
        raise HTTPException(status_code=500, detail="Dépendance manquante: openpyxl")

    items = await AdhesionRepository(db).list_admin_export_rows(
        status=status,
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("adhesions")
    ws.append(
        [
            "id",
            "nom",
            "prenom",
            "email",
            "tel_mobile",
            "cni",
            "region_domicile_nom",
            "departement_domicile_nom",
            "commune_domicile_nom",
            "region_militantisme_nom",
            "departement_militantisme_nom",
            "commune_militantisme_nom",
            "mode_paiement",
            "montant_adhesion",
            "paiement_confirme",
            "reference_paiement",
            "commissariat",
            "statut",
            "created_at",
        ]
    )

    for x in items:
        mode = x["mode_paiement"].value if hasattr(x["mode_paiement"], "value") else str(x["mode_paiement"])
        statut = x["statut"].value if hasattr(x["statut"], "value") else str(x["statut"])
        created_at = x["created_at"].isoformat() if x["created_at"] else ""
        ws.append(
            [
                str(x["id"]),
                x["nom"],
                x["prenom"],
                x["email"],
                x["tel_mobile"],
                x["cni"],
                x["region_domicile_nom"],
                x["departement_domicile_nom"],
                x["commune_domicile_nom"],
                x["region_militantisme_nom"],
                x["departement_militantisme_nom"],
                x["commune_militantisme_nom"],
                mode,
                x["montant_adhesion"],
                x["paiement_confirme"],
                x["reference_paiement"],
                x["commissariat"],
                statut,
                created_at,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    headers = {"Content-Disposition": 'attachment; filename="adhesions.xlsx"'}
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
