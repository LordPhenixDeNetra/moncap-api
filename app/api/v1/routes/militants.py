from __future__ import annotations

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
