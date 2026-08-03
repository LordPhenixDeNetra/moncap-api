from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.militants import GeoMode, MilitantsRepository, TimeInterval

Dimension = Literal["regions", "departements", "communes", "pays", "villes"]


@dataclass(frozen=True)
class MilitantsStatRow:
    id: uuid.UUID | None
    label: str
    count: int


@dataclass(frozen=True)
class MilitantsTimeseriesRow:
    period: str
    count: int


@dataclass(frozen=True)
class MilitantsDiasporaSplit:
    diaspora: int
    local: int


@dataclass(frozen=True)
class MilitantsHierarchyNode:
    id: uuid.UUID
    label: str
    count: int
    children: list["MilitantsHierarchyNode"]


class MilitantsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MilitantsRepository(session)

    async def count(
        self,
        *,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> int:
        return await self.repo.count_validated(commissariat=commissariat, from_date=from_date, to_date=to_date)

    async def stats(
        self,
        *,
        dimension: Dimension,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MilitantsStatRow]:
        if dimension == "regions":
            items = await self.repo.stats_by_region(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
            return [MilitantsStatRow(id=i, label=nom, count=count) for (i, nom, count) in items]
        if dimension == "departements":
            items = await self.repo.stats_by_departement(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
            return [MilitantsStatRow(id=i, label=nom, count=count) for (i, nom, count) in items]
        if dimension == "communes":
            items = await self.repo.stats_by_commune(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
            return [MilitantsStatRow(id=i, label=nom, count=count) for (i, nom, count) in items]
        if dimension == "pays":
            items = await self.repo.stats_by_pays(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
            return [MilitantsStatRow(id=i, label=nom, count=count) for (i, nom, count) in items]

        items = await self.repo.stats_by_ville(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
        return [MilitantsStatRow(id=None, label=label, count=count) for (label, count) in items]

    async def stats_commissariats(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MilitantsStatRow]:
        items = await self.repo.stats_by_commissariat(from_date=from_date, to_date=to_date)
        return [MilitantsStatRow(id=None, label=label, count=count) for (label, count) in items]

    async def diaspora_split(
        self,
        *,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> MilitantsDiasporaSplit:
        diaspora, local = await self.repo.diaspora_split(commissariat=commissariat, from_date=from_date, to_date=to_date)
        return MilitantsDiasporaSplit(diaspora=diaspora, local=local)

    async def timeseries(
        self,
        *,
        interval: TimeInterval,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MilitantsTimeseriesRow]:
        items = await self.repo.timeseries(interval=interval, commissariat=commissariat, from_date=from_date, to_date=to_date)
        return [MilitantsTimeseriesRow(period=x[0].date().isoformat(), count=x[1]) for x in items]

    async def hierarchy_regions_departements(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MilitantsHierarchyNode]:
        regions = await self.repo.stats_by_region(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
        deps = await self.repo.stats_by_departement_with_region(
            mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date
        )
        deps_by_region: dict[uuid.UUID, list[MilitantsHierarchyNode]] = {}
        for region_id, dep_id, dep_nom, count in deps:
            deps_by_region.setdefault(region_id, []).append(
                MilitantsHierarchyNode(id=dep_id, label=dep_nom, count=count, children=[])
            )
        return [
            MilitantsHierarchyNode(
                id=region_id,
                label=region_nom,
                count=count,
                children=deps_by_region.get(region_id, []),
            )
            for (region_id, region_nom, count) in regions
        ]

    async def hierarchy_departements_communes(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MilitantsHierarchyNode]:
        deps = await self.repo.stats_by_departement(mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date)
        communes = await self.repo.stats_by_commune_with_departement(
            mode=mode, commissariat=commissariat, from_date=from_date, to_date=to_date
        )
        communes_by_dep: dict[uuid.UUID, list[MilitantsHierarchyNode]] = {}
        for dep_id, commune_id, commune_nom, count in communes:
            communes_by_dep.setdefault(dep_id, []).append(
                MilitantsHierarchyNode(id=commune_id, label=commune_nom, count=count, children=[])
            )
        return [
            MilitantsHierarchyNode(
                id=dep_id,
                label=dep_nom,
                count=count,
                children=communes_by_dep.get(dep_id, []),
            )
            for (dep_id, dep_nom, count) in deps
        ]

    async def lookup_validated(
        self,
        *,
        adhesion_id: uuid.UUID | None,
        email: str | None,
        cni: str | None,
        tel_mobile: str | None,
        carte_pastef: str | None,
    ):
        try:
            adhesion = await self.repo.lookup_validated(
                adhesion_id=adhesion_id,
                email=email,
                cni=cni,
                tel_mobile=tel_mobile,
                carte_pastef=carte_pastef,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Un seul critère de recherche doit être fourni")

        if not adhesion:
            raise HTTPException(status_code=404, detail="Militant introuvable")
        return adhesion
