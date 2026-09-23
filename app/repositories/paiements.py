from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paiements import (
    CotisationMensuelle,
    CotisationStatut,
    ParametrePaiement,
    PeriodePaiement,
    StatutTransactionKopar,
    TransactionKopar,
)


class ParametrePaiementRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_for_code_at(
        self, code: str, at_date: date
    ) -> ParametrePaiement | None:
        q = (
            select(ParametrePaiement)
            .where(ParametrePaiement.code == code)
            .where(ParametrePaiement.date_effet <= at_date)
            .where(
                or_(
                    ParametrePaiement.date_fin_effet.is_(None),
                    ParametrePaiement.date_fin_effet >= at_date,
                )
            )
            .order_by(desc(ParametrePaiement.date_effet))
            .limit(1)
        )
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def list_all_for_code(self, code: str) -> list[ParametrePaiement]:
        q = (
            select(ParametrePaiement)
            .where(ParametrePaiement.code == code)
            .order_by(desc(ParametrePaiement.date_effet))
        )
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def list_all(self) -> list[ParametrePaiement]:
        q = select(ParametrePaiement).order_by(
            ParametrePaiement.code, desc(ParametrePaiement.date_effet)
        )
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def create(self, param: ParametrePaiement) -> ParametrePaiement:
        self.session.add(param)
        await self.session.flush()
        return param

    async def update(
        self, param_id: uuid.UUID, data: dict[str, Any]
    ) -> ParametrePaiement | None:
        param = await self.session.get(ParametrePaiement, param_id)
        if not param:
            return None
        for k, v in data.items():
            setattr(param, k, v)
        await self.session.flush()
        return param

    async def close_current_and_insert(
        self,
        code: str,
        nouveau: ParametrePaiement,
        date_fin_existant: date,
    ) -> ParametrePaiement:
        prev = await self.get_active_for_code_at(
            code,
            nouveau.date_effet
            - (
                __import__("datetime").timedelta(days=1)
                if nouveau.date_effet.day > 1
                else __import__("datetime").timedelta(days=0)
            ),
        )
        if prev and (prev.date_fin_effet is None or prev.date_fin_effet > date_fin_existant):
            prev.date_fin_effet = date_fin_existant
            await self.session.flush()
        self.session.add(nouveau)
        await self.session.flush()
        return nouveau


class CotisationMensuelleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, cid: uuid.UUID) -> CotisationMensuelle | None:
        return await self.session.get(CotisationMensuelle, cid)

    async def get_for_adherent_mois(
        self, adhesion_id: uuid.UUID, annee: int, mois: int
    ) -> CotisationMensuelle | None:
        q = select(CotisationMensuelle).where(
            CotisationMensuelle.adhesion_id == adhesion_id,
            CotisationMensuelle.annee == annee,
            CotisationMensuelle.mois == mois,
        )
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def list_for_adherent(
        self, adhesion_id: uuid.UUID, limit: int = 24
    ) -> list[CotisationMensuelle]:
        q = (
            select(CotisationMensuelle)
            .where(CotisationMensuelle.adhesion_id == adhesion_id)
            .order_by(
                desc(CotisationMensuelle.annee), desc(CotisationMensuelle.mois)
            )
            .limit(limit)
        )
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def list_for_mois(
        self,
        annee: int,
        mois: int,
        statut: CotisationStatut | None = None,
        region_id: uuid.UUID | None = None,
        commissariat: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CotisationMensuelle]:
        from app.models.adhesion import Adhesion

        q = select(CotisationMensuelle).join(
            Adhesion, Adhesion.id == CotisationMensuelle.adhesion_id
        )
        conds = [CotisationMensuelle.annee == annee, CotisationMensuelle.mois == mois]
        if statut is not None:
            conds.append(CotisationMensuelle.statut == statut)
        if region_id is not None:
            conds.append(
                (Adhesion.region_domicile_id == region_id)
                | (Adhesion.region_militantisme_id == region_id)
            )
        if commissariat:
            conds.append(Adhesion.commissariat == commissariat)
        q = q.where(and_(*conds)).order_by(desc(CotisationMensuelle.created_at)).offset(offset).limit(limit)
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def count_for_mois(
        self,
        annee: int,
        mois: int,
        statut: CotisationStatut | None = None,
    ) -> int:
        q = select(func.count(CotisationMensuelle.id)).where(
            CotisationMensuelle.annee == annee, CotisationMensuelle.mois == mois
        )
        if statut is not None:
            q = q.where(CotisationMensuelle.statut == statut)
        res = await self.session.execute(q)
        return int(res.scalar_one())

    async def create(self, c: CotisationMensuelle) -> CotisationMensuelle:
        self.session.add(c)
        await self.session.flush()
        return c

    async def mark_paid(
        self,
        cid: uuid.UUID,
        *,
        reference_paiement: str | None = None,
        mode_paiement: str | None = None,
        paiement_date: datetime | None = None,
    ) -> CotisationMensuelle | None:
        c = await self.get_by_id(cid)
        if not c:
            return None
        c.statut = CotisationStatut.payee
        c.paiement_date = paiement_date or datetime.now(timezone.utc)
        if reference_paiement:
            c.reference_paiement = reference_paiement
        if mode_paiement:
            c.mode_paiement = mode_paiement
        await self.session.flush()
        return c

    async def mark_manuel(
        self,
        cid: uuid.UUID,
        *,
        user_id: uuid.UUID,
        note: str | None = None,
        reference_paiement: str | None = None,
    ) -> CotisationMensuelle | None:
        c = await self.get_by_id(cid)
        if not c:
            return None
        c.statut = CotisationStatut.payee
        c.paiement_date = datetime.now(timezone.utc)
        c.paiement_manuel = True
        c.paiement_manuel_par_user_id = user_id
        if note:
            c.paiement_manuel_note = note
        if reference_paiement:
            c.reference_paiement = reference_paiement
        c.mode_paiement = "manuel"
        await self.session.flush()
        return c

    @staticmethod
    def calculer_mois_consecutifs(
        from_annee: int, from_mois: int, nb_mois: int
    ) -> list[tuple[int, int]]:
        """Calcule N (annee, mois) consécutifs à partir d'un point de départ (mois inclus)."""
        result: list[tuple[int, int]] = []
        if nb_mois is None or nb_mois < 1:
            nb_mois = 1
        an, mo = int(from_annee), int(from_mois)
        for _ in range(int(nb_mois)):
            result.append((an, mo))
            mo += 1
            if mo > 12:
                mo = 1
                an += 1
        return result

    async def get_or_create_for_adherent_mois(
        self,
        adhesion_id: uuid.UUID,
        annee: int,
        mois: int,
        *,
        montant_defaut: int | None = None,
        devise: str = "XOF",
    ) -> CotisationMensuelle:
        c = await self.get_for_adherent_mois(adhesion_id, annee, mois)
        if c is not None:
            return c
        c = CotisationMensuelle(
            adhesion_id=adhesion_id,
            annee=annee,
            mois=mois,
            montant=int(montant_defaut or 0),
            devise=devise or "XOF",
            statut=CotisationStatut.en_attente,
        )
        self.session.add(c)
        await self.session.flush()
        return c

    async def mark_paid_periode(
        self,
        tx: TransactionKopar,
        *,
        reference_paiement: str,
        mode_paiement: str,
        paiement_date: datetime | None = None,
        paiement_manuel_user_id: uuid.UUID | None = None,
        paiement_manuel_note: str | None = None,
    ) -> list[CotisationMensuelle]:
        """
        Marque N=tx.periode_mois lignes mensuelles comme payées (idempotent : skippe les payées).

        tx.cotisation_id = PREMIER mois de la période (point d'ancrage).
        Cas spéciaux :
          • tx.periode_mois NULL/1 → exactement 1 ligne (comme aujourd'hui, retro OK)
          • tx.periode_mois IN (3,6,12) → N lignes consécutives
          • ligne inexistante (mois futurs pas encore générés par CRON) → CRÉÉE PUIS marquée
          • ligne déjà payée → SKIP sans erreur (double webhook / double paiement OK)
        """
        result: list[CotisationMensuelle] = []
        if tx is None:
            return result
        periode = PeriodePaiement.normaliser(tx.periode_mois)
        if tx.type_transaction.value != "cotisation" if hasattr(tx.type_transaction, "value") else str(tx.type_transaction) != "cotisation":
            return result
        premier = None
        if tx.cotisation_id:
            premier = await self.get_by_id(tx.cotisation_id)
        if premier is None:
            return result
        adhesion_id = premier.adhesion_id
        from_annee = premier.annee
        from_mois = premier.mois
        if tx.premiere_annee_couverte and tx.premier_mois_couverte:
            from_annee = int(tx.premiere_annee_couverte)
            from_mois = int(tx.premier_mois_couverte)
        liste_mois = self.calculer_mois_consecutifs(from_annee, from_mois, periode)
        paiement_ts = paiement_date or datetime.now(timezone.utc)
        ref_p = str(reference_paiement or tx.kopar_token or "")[:200] or None
        mode_p = str(mode_paiement or "kopar") or None
        montant_defaut_mois = premier.montant or getattr(premier, "montant", None) or 0
        devise_mois = premier.devise or "XOF"
        manuel = bool(paiement_manuel_user_id)
        for (an, mo) in liste_mois:
            c = await self.get_or_create_for_adherent_mois(
                adhesion_id,
                an,
                mo,
                montant_defaut=montant_defaut_mois,
                devise=devise_mois,
            )
            statut_valeur = c.statut.value if hasattr(c.statut, "value") else str(c.statut)
            if statut_valeur == "payee":
                continue
            c.statut = CotisationStatut.payee
            c.paiement_date = paiement_ts
            if ref_p:
                c.reference_paiement = ref_p
            if mode_p:
                c.mode_paiement = mode_p
            if manuel:
                c.paiement_manuel = True
                c.paiement_manuel_par_user_id = paiement_manuel_user_id
                if paiement_manuel_note:
                    c.paiement_manuel_note = str(paiement_manuel_note)[:500]
            await self.session.flush()
            result.append(c)
        return result

    async def mark_manuel_periode(
        self,
        premier_cotisation_id: uuid.UUID,
        periode_mois: int,
        *,
        user_id: uuid.UUID,
        note: str | None = None,
        reference_paiement: str | None = None,
    ) -> list[CotisationMensuelle]:
        """Paiement MANUEL ADMIN multi-périodes (pas de transaction Kopar)."""
        premier = await self.get_by_id(premier_cotisation_id)
        if premier is None:
            return []
        fake_tx = TransactionKopar(
            id=uuid.uuid4(),
            type_transaction=TypeTransactionKopar.cotisation,
            cotisation_id=premier.id,
            adhesion_id=premier.adhesion_id,
            periode_mois=PeriodePaiement.normaliser(periode_mois),
            premiere_annee_couverte=premier.annee,
            premier_mois_couverte=premier.mois,
            kopar_token="",
            command_ref="",
            command_name="",
            montant=0,
        )
        return await self.mark_paid_periode(
            fake_tx,
            reference_paiement=str(reference_paiement or "")[:200] or f"MANUEL-{str(premier_cotisation_id)[:8].upper()}",
            mode_paiement="manuel",
            paiement_date=datetime.now(timezone.utc),
            paiement_manuel_user_id=user_id,
            paiement_manuel_note=note,
        )

    async def list_ids_impayes_mois(
        self,
        annee: int,
        mois: int,
        *,
        only_not_relance_1: bool = False,
        only_not_relance_2: bool = False,
        limit: int = 500,
    ) -> list[uuid.UUID]:
        q = select(CotisationMensuelle.id).where(
            CotisationMensuelle.annee == annee,
            CotisationMensuelle.mois == mois,
            CotisationMensuelle.statut == CotisationStatut.en_attente,
        )
        if only_not_relance_1:
            q = q.where(CotisationMensuelle.relance_envoyee_1 == False)
        if only_not_relance_2:
            q = q.where(CotisationMensuelle.relance_envoyee_2 == False)
        q = q.limit(limit)
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def mark_relance_envoyee(self, cid: uuid.UUID, niveau: int) -> None:
        c = await self.get_by_id(cid)
        if not c:
            return
        if niveau >= 1:
            c.relance_envoyee_1 = True
        if niveau >= 2:
            c.relance_envoyee_2 = True
        await self.session.flush()


class TransactionKoparRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_token(self, token: str) -> TransactionKopar | None:
        q = select(TransactionKopar).where(TransactionKopar.kopar_token == token)
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def get_by_command_ref(self, command_ref: str) -> list[TransactionKopar]:
        q = (
            select(TransactionKopar)
            .where(TransactionKopar.command_ref == command_ref)
            .order_by(desc(TransactionKopar.created_at))
        )
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def create(self, t: TransactionKopar) -> TransactionKopar:
        self.session.add(t)
        await self.session.flush()
        return t

    async def update_statut(
        self,
        tid: uuid.UUID,
        statut: StatutTransactionKopar,
        *,
        service: str | None = None,
        raw_response: dict | None = None,
        kopar_id: str | None = None,
    ) -> TransactionKopar | None:
        t = await self.session.get(TransactionKopar, tid)
        if not t:
            return None
        t.statut = statut
        if service:
            t.service = service
        if raw_response is not None:
            t.raw_response = raw_response
        if kopar_id:
            t.kopar_id = kopar_id
        await self.session.flush()
        return t

    async def update_after_webhook(
        self,
        tid: uuid.UUID,
        statut: StatutTransactionKopar,
        *,
        webhook_body: dict,
        customer_phone: str | None = None,
        customer_email: str | None = None,
    ) -> TransactionKopar | None:
        t = await self.session.get(TransactionKopar, tid)
        if not t:
            return None
        t.statut = statut
        t.last_webhook_body = webhook_body
        t.last_webhook_received_at = datetime.now(timezone.utc)
        if customer_phone:
            t.customer_phone = customer_phone
        if customer_email:
            t.customer_email = customer_email
        await self.session.flush()
        return t

    async def sommer_montants(
        self,
        *,
        statut: StatutTransactionKopar | None = None,
        type_transaction: "TypeTransactionKopar | None" = None,
        adhesion_id: uuid.UUID | None = None,
        cotisation_id: uuid.UUID | None = None,
    ) -> int:
        """
        Somme COALESCE(SUM(montant), 0) des transactions Kopar correspondant
        aux filtres fournis. Permet de déterminer dynamiquement si un adhérent
        a bien réglé ses frais d'adhésion (évite les incohérences de
        adhesion.paiement_confirme qui n'est pas toujours mis à jour en back-office
        pour les paiements manuels anciens).
        """
        q = select(func.coalesce(func.sum(TransactionKopar.montant), 0))
        conds: list = []
        if statut is not None:
            conds.append(TransactionKopar.statut == statut)
        if type_transaction is not None:
            conds.append(TransactionKopar.type_transaction == type_transaction)
        if adhesion_id is not None:
            conds.append(TransactionKopar.adhesion_id == adhesion_id)
        if cotisation_id is not None:
            conds.append(TransactionKopar.cotisation_id == cotisation_id)
        if conds:
            q = q.where(and_(*conds))
        res = await self.session.execute(q)
        raw = res.scalar_one() or 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0
