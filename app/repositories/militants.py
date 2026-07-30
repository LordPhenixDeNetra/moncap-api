from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus
from app.models.geo import Commune, Departement, Pays, Region

GeoMode = Literal["domicile", "militantisme"]
TimeInterval = Literal["day", "week", "month"]


class MilitantsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _validated_where(
        self,
        *,
        commissariat: str | None,
        from_date: date | None,
        to_date: date | None,
    ):
        where = [Adhesion.statut == AdhesionStatus.validee]
        if commissariat:
            where.append(Adhesion.commissariat == commissariat)
        if from_date:
            where.append(Adhesion.created_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))
        if to_date:
            where.append(Adhesion.created_at <= datetime.combine(to_date, datetime.max.time(), tzinfo=timezone.utc))
        return and_(*where)

    async def count_validated(
        self,
        *,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> int:
        qy = select(func.count()).select_from(Adhesion).where(
            self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date)
        )
        return int((await self.session.execute(qy)).scalar_one())

    async def stats_by_region(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[uuid.UUID, str, int]]:
        adhesion_region_id = Adhesion.region_domicile_id if mode == "domicile" else Adhesion.region_militantisme_id
        qy = (
            select(Region.id, Region.nom, func.count().label("count"))
            .select_from(Adhesion)
            .join(Region, Region.id == adhesion_region_id)
            .where(adhesion_region_id.is_not(None))
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(Region.id, Region.nom)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(r[0], r[1], int(r[2])) for r in res.all()]

    async def stats_by_departement(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[uuid.UUID, str, int]]:
        adhesion_departement_id = (
            Adhesion.departement_domicile_id if mode == "domicile" else Adhesion.departement_militantisme_id
        )
        qy = (
            select(Departement.id, Departement.nom, func.count().label("count"))
            .select_from(Adhesion)
            .join(Departement, Departement.id == adhesion_departement_id)
            .where(adhesion_departement_id.is_not(None))
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(Departement.id, Departement.nom)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(r[0], r[1], int(r[2])) for r in res.all()]

    async def stats_by_departement_with_region(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[uuid.UUID, uuid.UUID, str, int]]:
        adhesion_departement_id = (
            Adhesion.departement_domicile_id if mode == "domicile" else Adhesion.departement_militantisme_id
        )
        qy = (
            select(Departement.region_id, Departement.id, Departement.nom, func.count().label("count"))
            .select_from(Adhesion)
            .join(Departement, Departement.id == adhesion_departement_id)
            .where(adhesion_departement_id.is_not(None))
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(Departement.region_id, Departement.id, Departement.nom)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(r[0], r[1], r[2], int(r[3])) for r in res.all()]

    async def stats_by_commune(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[uuid.UUID, str, int]]:
        adhesion_commune_id = Adhesion.commune_domicile_id if mode == "domicile" else Adhesion.commune_militantisme_id
        qy = (
            select(Commune.id, Commune.nom, func.count().label("count"))
            .select_from(Adhesion)
            .join(Commune, Commune.id == adhesion_commune_id)
            .where(adhesion_commune_id.is_not(None))
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(Commune.id, Commune.nom)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(r[0], r[1], int(r[2])) for r in res.all()]

    async def stats_by_commune_with_departement(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[uuid.UUID, uuid.UUID, str, int]]:
        adhesion_commune_id = Adhesion.commune_domicile_id if mode == "domicile" else Adhesion.commune_militantisme_id
        qy = (
            select(Commune.departement_id, Commune.id, Commune.nom, func.count().label("count"))
            .select_from(Adhesion)
            .join(Commune, Commune.id == adhesion_commune_id)
            .where(adhesion_commune_id.is_not(None))
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(Commune.departement_id, Commune.id, Commune.nom)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(r[0], r[1], r[2], int(r[3])) for r in res.all()]

    async def stats_by_pays(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[uuid.UUID, str, int]]:
        adhesion_pays_id = Adhesion.pays_domicile_id if mode == "domicile" else Adhesion.pays_militantisme_id
        qy = (
            select(Pays.id, Pays.nom, func.count().label("count"))
            .select_from(Adhesion)
            .join(Pays, Pays.id == adhesion_pays_id)
            .where(adhesion_pays_id.is_not(None))
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(Pays.id, Pays.nom)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(r[0], r[1], int(r[2])) for r in res.all()]

    async def stats_by_ville(
        self,
        *,
        mode: GeoMode,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[str, int]]:
        ville_col = Adhesion.ville_domicile if mode == "domicile" else Adhesion.ville_militantisme
        label = func.lower(func.trim(ville_col)).label("label")
        qy = (
            select(label, func.count().label("count"))
            .select_from(Adhesion)
            .where(ville_col.is_not(None))
            .where(func.trim(ville_col) != "")
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(label)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(str(r[0]), int(r[1])) for r in res.all()]

    async def stats_by_commissariat(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[str, int]]:
        label = func.trim(Adhesion.commissariat).label("label")
        qy = (
            select(label, func.count().label("count"))
            .select_from(Adhesion)
            .where(Adhesion.commissariat.is_not(None))
            .where(func.trim(Adhesion.commissariat) != "")
            .where(self._validated_where(commissariat=None, from_date=from_date, to_date=to_date))
            .group_by(label)
            .order_by(desc("count"))
        )
        res = await self.session.execute(qy)
        return [(str(r[0]), int(r[1])) for r in res.all()]

    async def diaspora_split(
        self,
        *,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[int, int]:
        where = self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date)

        qy_diaspora = select(func.count()).select_from(Adhesion).where(where).where(Adhesion.est_diaspora.is_(True))
        qy_local = select(func.count()).select_from(Adhesion).where(where).where(Adhesion.est_diaspora.is_(False))

        diaspora = int((await self.session.execute(qy_diaspora)).scalar_one())
        local = int((await self.session.execute(qy_local)).scalar_one())
        return diaspora, local

    async def timeseries(
        self,
        *,
        interval: TimeInterval,
        commissariat: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[datetime, int]]:
        bucket = func.date_trunc(interval, Adhesion.created_at).label("bucket")
        qy = (
            select(bucket, func.count().label("count"))
            .select_from(Adhesion)
            .where(self._validated_where(commissariat=commissariat, from_date=from_date, to_date=to_date))
            .group_by(bucket)
            .order_by(bucket)
        )
        res = await self.session.execute(qy)
        return [(r[0], int(r[1])) for r in res.all()]
