from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.db.session import get_db
from app.models.enums import AppRole
from app.schemas.militants import (
    MilitantsCountResponse,
    MilitantsDiasporaResponse,
    MilitantsHierarchyResponse,
    MilitantLookupResponse,
    MilitantsStatsResponse,
    MilitantsTimeseriesResponse,
)
from app.services.militants import MilitantsService

GeoMode = Literal["domicile", "militantisme"]
Dimension = Literal["regions", "departements", "communes", "pays", "villes"]
TimeInterval = Literal["day", "week", "month"]
HierarchyLevel = Literal["regions_departements", "departements_communes"]

router = APIRouter(
    prefix="/militants",
    dependencies=[Depends(require_roles(AppRole.admin, AppRole.comite_accueil, AppRole.comite_directoire))],
)

public_router = APIRouter(prefix="/militants")


@router.get(
    "/count",
    response_model=MilitantsCountResponse,
    summary="Compter les militants",
    description="Retourne le nombre d'adhérents dont la demande est validée (statut=validee).",
)
async def count_militants(
    commissariat: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    total = await MilitantsService(db).count(commissariat=commissariat, from_date=from_date, to_date=to_date)
    return {"data": {"total": total}}


@router.get(
    "/stats/commissariats",
    response_model=MilitantsStatsResponse,
    summary="Statistiques militants par commissariat",
    description="Retourne des comptages de militants (statut=validee) groupés par commissariat.",
)
async def militants_stats_commissariats(
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    rows = await MilitantsService(db).stats_commissariats(from_date=from_date, to_date=to_date)
    return {"data": [{"id": r.id, "label": r.label, "count": r.count} for r in rows]}


@router.get(
    "/stats/diaspora",
    response_model=MilitantsDiasporaResponse,
    summary="Répartition diaspora vs local",
    description="Retourne les comptages de militants (statut=validee) entre diaspora et non-diaspora.",
)
async def militants_stats_diaspora(
    commissariat: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    split = await MilitantsService(db).diaspora_split(commissariat=commissariat, from_date=from_date, to_date=to_date)
    return {"data": {"diaspora": split.diaspora, "local": split.local}}

@router.get(
    "/stats/{dimension}",
    response_model=MilitantsStatsResponse,
    summary="Statistiques militants",
    description="Retourne des agrégations (comptages) de militants par région/département/commune/pays/ville.",
)
async def militants_stats(
    dimension: Dimension,
    mode: GeoMode = "domicile",
    commissariat: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    rows = await MilitantsService(db).stats(
        dimension=dimension,
        mode=mode,
        commissariat=commissariat,
        from_date=from_date,
        to_date=to_date,
    )
    return {"data": [{"id": r.id, "label": r.label, "count": r.count} for r in rows]}


@router.get(
    "/timeseries",
    response_model=MilitantsTimeseriesResponse,
    summary="Série temporelle militants",
    description="Retourne une série temporelle des militants validés (par jour/semaine/mois).",
)
async def militants_timeseries(
    interval: TimeInterval = "month",
    commissariat: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    rows = await MilitantsService(db).timeseries(
        interval=interval, commissariat=commissariat, from_date=from_date, to_date=to_date
    )
    return {"data": [{"period": r.period, "count": r.count} for r in rows]}


@router.get(
    "/hierarchy",
    response_model=MilitantsHierarchyResponse,
    summary="Hiérarchie géographique",
    description="Retourne une vue hiérarchique: régions→départements ou départements→communes pour les militants validés.",
)
async def militants_hierarchy(
    level: HierarchyLevel = "regions_departements",
    mode: GeoMode = "domicile",
    commissariat: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = MilitantsService(db)
    if level == "departements_communes":
        nodes = await svc.hierarchy_departements_communes(
            mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date
        )
    else:
        nodes = await svc.hierarchy_regions_departements(
            mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date
        )
    return {
        "data": [
            {
                "id": n.id,
                "label": n.label,
                "count": n.count,
                "children": [
                    {"id": c.id, "label": c.label, "count": c.count, "children": []} for c in n.children
                ],
            }
            for n in nodes
        ]
    }


@public_router.get(
    "/lookup",
    response_model=MilitantLookupResponse,
    summary="Récupérer un militant validé",
    description="Retourne la fiche d'un adhérent validé (statut=validee) via un critère unique (id/email/cni/tel_mobile/carte_pastef).",
)
async def lookup_militant(
    id: uuid.UUID | None = None,
    email: str | None = None,
    cni: str | None = None,
    tel_mobile: str | None = None,
    carte_pastef: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    adhesion = await MilitantsService(db).lookup_validated(
        adhesion_id=id,
        email=email,
        cni=cni,
        tel_mobile=tel_mobile,
        carte_pastef=carte_pastef,
    )
    return {
        "data": {
            "id": adhesion.id,
            "nom": adhesion.nom,
            "prenom": adhesion.prenom,
            "email": adhesion.email,
            "tel_mobile": adhesion.tel_mobile,
            "cni": adhesion.cni,
            "carte_pastef": adhesion.carte_pastef,
            "photo_url": adhesion.photo_url,
            "profile_photo_url": adhesion.profile_photo_url,
            "commissariat": adhesion.commissariat,
            "region_domicile_id": adhesion.region_domicile_id,
            "departement_domicile_id": adhesion.departement_domicile_id,
            "commune_domicile_id": adhesion.commune_domicile_id,
            "pays_domicile_id": adhesion.pays_domicile_id,
            "ville_domicile": adhesion.ville_domicile,
            "region_domicile": adhesion.region_domicile,
            "departement_domicile": adhesion.departement_domicile,
            "commune_domicile": adhesion.commune_domicile,
            "pays_domicile": adhesion.pays_domicile,
        }
    }
