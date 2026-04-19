from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus


class AdhesionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _with_geo(self):
        return (
            selectinload(Adhesion.region_domicile),
            selectinload(Adhesion.departement_domicile),
            selectinload(Adhesion.commune_domicile),
            selectinload(Adhesion.region_militantisme),
            selectinload(Adhesion.departement_militantisme),
            selectinload(Adhesion.commune_militantisme),
        )

    async def get_by_idempotency_key(self, key: str) -> Adhesion | None:
        res = await self.session.execute(select(Adhesion).where(Adhesion.idempotency_key == key))
        return res.scalar_one_or_none()

    async def create(self, adhesion: Adhesion) -> Adhesion:
        self.session.add(adhesion)
        await self.session.flush()
        return adhesion

    async def get_by_id(self, adhesion_id: uuid.UUID) -> Adhesion | None:
        qy = select(Adhesion).where(Adhesion.id == adhesion_id).options(*self._with_geo())
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def get_latest_by_email(self, email: str) -> Adhesion | None:
        qy = (
            select(Adhesion)
            .where(Adhesion.email == email)
            .order_by(desc(Adhesion.created_at))
            .limit(1)
            .options(*self._with_geo())
        )
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def get_latest_by_cni(self, cni: str) -> Adhesion | None:
        qy = (
            select(Adhesion)
            .where(Adhesion.cni == cni)
            .order_by(desc(Adhesion.created_at))
            .limit(1)
            .options(*self._with_geo())
        )
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def get_latest_by_tel_mobile(self, tel_mobile: str) -> Adhesion | None:
        qy = (
            select(Adhesion)
            .where(Adhesion.tel_mobile == tel_mobile)
            .order_by(desc(Adhesion.created_at))
            .limit(1)
            .options(*self._with_geo())
        )
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def list_by_email(self, email: str) -> list[Adhesion]:
        res = await self.session.execute(
            select(Adhesion).where(Adhesion.email == email).order_by(desc(Adhesion.created_at))
        )
        return list(res.scalars().all())

    async def list_admin(
        self,
        *,
        limit: int,
        offset: int,
        status: AdhesionStatus | None,
        commissariat: str | None,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[Adhesion], int]:
        where = []
        if status:
            where.append(Adhesion.statut == status)
        if commissariat:
            where.append(Adhesion.commissariat == commissariat)
        if from_date:
            where.append(Adhesion.created_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))
        if to_date:
            where.append(Adhesion.created_at <= datetime.combine(to_date, datetime.max.time(), tzinfo=timezone.utc))
        if q:
            like = f"%{q.strip()}%"
            where.append(
                or_(
                    Adhesion.nom.ilike(like),
                    Adhesion.prenom.ilike(like),
                    Adhesion.email.ilike(like),
                    Adhesion.cni.ilike(like),
                )
            )

        base = select(Adhesion)
        if where:
            base = base.where(and_(*where))

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        qy = base.order_by(desc(Adhesion.created_at)).limit(limit).offset(offset)
        items = list((await self.session.execute(qy)).scalars().all())
        return items, int(total)

    async def update_status(
        self,
        *,
        adhesion_id: uuid.UUID,
        statut: AdhesionStatus,
        motif_rejet: str | None,
    ) -> int:
        res = await self.session.execute(
            update(Adhesion)
            .where(Adhesion.id == adhesion_id)
            .values(statut=statut, motif_rejet=motif_rejet, updated_at=func.now())
        )
        return res.rowcount or 0
