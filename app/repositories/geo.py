from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geo import Commune, Departement, Region


class GeoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_regions(self) -> list[Region]:
        res = await self.session.execute(select(Region).order_by(Region.nom.asc()))
        return list(res.scalars().all())

    async def list_departements(self, *, region_id: uuid.UUID) -> list[Departement]:
        res = await self.session.execute(
            select(Departement).where(Departement.region_id == region_id).order_by(Departement.nom.asc())
        )
        return list(res.scalars().all())

    async def list_communes(self, *, departement_id: uuid.UUID) -> list[Commune]:
        res = await self.session.execute(
            select(Commune).where(Commune.departement_id == departement_id).order_by(Commune.nom.asc())
        )
        return list(res.scalars().all())

    async def get_region(self, region_id: uuid.UUID) -> Region | None:
        res = await self.session.execute(select(Region).where(Region.id == region_id))
        return res.scalar_one_or_none()

    async def get_departement(self, departement_id: uuid.UUID) -> Departement | None:
        res = await self.session.execute(select(Departement).where(Departement.id == departement_id))
        return res.scalar_one_or_none()

    async def get_commune(self, commune_id: uuid.UUID) -> Commune | None:
        res = await self.session.execute(select(Commune).where(Commune.id == commune_id))
        return res.scalar_one_or_none()

