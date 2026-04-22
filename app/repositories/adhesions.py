from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql import Select

from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus
from app.models.geo import Commune, Departement, Region


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

    def _apply_admin_filters(
        self,
        qy: Select,
        *,
        status: AdhesionStatus | None,
        commissariat: str | None,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> Select:
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

        if where:
            qy = qy.where(and_(*where))
        return qy

    async def list_admin_export_rows(
        self,
        *,
        status: AdhesionStatus | None,
        commissariat: str | None,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
        limit: int = 100000,
    ) -> list[dict]:
        region_domicile = aliased(Region)
        departement_domicile = aliased(Departement)
        commune_domicile = aliased(Commune)
        region_militantisme = aliased(Region)
        departement_militantisme = aliased(Departement)
        commune_militantisme = aliased(Commune)

        qy = (
            select(
                Adhesion.id.label("id"),
                Adhesion.nom.label("nom"),
                Adhesion.prenom.label("prenom"),
                Adhesion.email.label("email"),
                Adhesion.tel_mobile.label("tel_mobile"),
                Adhesion.cni.label("cni"),
                region_domicile.nom.label("region_domicile_nom"),
                departement_domicile.nom.label("departement_domicile_nom"),
                commune_domicile.nom.label("commune_domicile_nom"),
                region_militantisme.nom.label("region_militantisme_nom"),
                departement_militantisme.nom.label("departement_militantisme_nom"),
                commune_militantisme.nom.label("commune_militantisme_nom"),
                Adhesion.mode_paiement.label("mode_paiement"),
                Adhesion.montant_adhesion.label("montant_adhesion"),
                Adhesion.paiement_confirme.label("paiement_confirme"),
                Adhesion.reference_paiement.label("reference_paiement"),
                Adhesion.commissariat.label("commissariat"),
                Adhesion.statut.label("statut"),
                Adhesion.created_at.label("created_at"),
            )
            .outerjoin(region_domicile, region_domicile.id == Adhesion.region_domicile_id)
            .outerjoin(departement_domicile, departement_domicile.id == Adhesion.departement_domicile_id)
            .outerjoin(commune_domicile, commune_domicile.id == Adhesion.commune_domicile_id)
            .outerjoin(region_militantisme, region_militantisme.id == Adhesion.region_militantisme_id)
            .outerjoin(departement_militantisme, departement_militantisme.id == Adhesion.departement_militantisme_id)
            .outerjoin(commune_militantisme, commune_militantisme.id == Adhesion.commune_militantisme_id)
        )

        qy = self._apply_admin_filters(
            qy,
            status=status,
            commissariat=commissariat,
            q=q,
            from_date=from_date,
            to_date=to_date,
        ).order_by(desc(Adhesion.created_at)).limit(limit)

        res = await self.session.execute(qy)
        return [dict(r) for r in res.mappings().all()]

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

    async def update_payment(
        self,
        *,
        adhesion_id: uuid.UUID,
        paiement_confirme: bool,
        reference_paiement: str | None,
    ) -> int:
        res = await self.session.execute(
            update(Adhesion)
            .where(Adhesion.id == adhesion_id)
            .values(
                paiement_confirme=paiement_confirme,
                reference_paiement=reference_paiement,
                updated_at=func.now(),
            )
        )
        return res.rowcount or 0
