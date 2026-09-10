from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus
from app.models.paiements import (
    CotisationMensuelle,
    CotisationStatut,
    ParametrePaiement,
    ParametrePaiementCode,
)
from app.repositories.adhesions import AdhesionRepository
from app.repositories.paiements import (
    CotisationMensuelleRepository,
    ParametrePaiementRepository,
)


@dataclass(frozen=True)
class RapportCotisationMois:
    annee: int
    mois: int
    total: int
    payes: int
    en_attente: int
    echues: int
    montant_total: int
    montant_percu: int


class ParametresPaiementService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ParametrePaiementRepository(session)

    async def get_montant(
        self,
        code: ParametrePaiementCode | str,
        at_date: date | None = None,
    ) -> int:
        dt = at_date or date.today()
        p = await self.repo.get_active_for_code_at(str(code), dt)
        if p and p.montant_fcfa is not None:
            return p.montant_fcfa
        settings = get_settings()
        fallback = {
            ParametrePaiementCode.adhesion_initiale.value: settings.default_adhesion_fcfa,
            ParametrePaiementCode.cotisation_mensuelle.value: settings.default_cotisation_mensuelle_fcfa,
        }
        if str(code) in fallback:
            return fallback[str(code)]
        raise HTTPException(
            status_code=500,
            detail=f"Paramètre paiement '{code}' introuvable à la date {dt}",
        )

    async def get_regle_premiere_cotisation(self) -> str:
        p = await self.repo.get_active_for_code_at(
            ParametrePaiementCode.regle_date_premiere_cotisation.value,
            date.today(),
        )
        if p and p.valeur_texte:
            return p.valeur_texte
        return "jour_15"

    async def get_all(self) -> list[ParametrePaiement]:
        return await self.repo.list_all()

    async def list_for_code(self, code: str) -> list[ParametrePaiement]:
        return await self.repo.list_all_for_code(code)

    async def creer_parametre(self, **kwargs) -> ParametrePaiement:
        p = ParametrePaiement(**kwargs)
        return await self.repo.create(p)

    async def modifier_parametre(
        self, pid: uuid.UUID, data: dict
    ) -> ParametrePaiement | None:
        return await self.repo.update(pid, data)

    async def determiner_premier_mois_cotisation(
        self, date_validation: date
    ) -> tuple[int, int]:
        regle = await self.get_regle_premiere_cotisation()
        annee = date_validation.year
        mois = date_validation.month
        if regle.startswith("jour_"):
            try:
                jour_seuil = int(regle.split("_")[1])
            except Exception:
                jour_seuil = 15
            if date_validation.day <= jour_seuil:
                return (annee, mois)
            mois_suivant = mois + 1
            annee_suivante = annee
            if mois_suivant > 12:
                mois_suivant = 1
                annee_suivante = annee + 1
            return (annee_suivante, mois_suivant)
        if regle == "mois_suivant":
            mois_suivant = mois + 1
            annee_suivante = annee
            if mois_suivant > 12:
                mois_suivant = 1
                annee_suivante = annee + 1
            return (annee_suivante, mois_suivant)
        return (annee, mois)

    async def seed_defaults_if_empty(self) -> None:
        today = date.today()
        codes_a_seeder: list[tuple[str, str, int | None, str | None]] = [
            (
                ParametrePaiementCode.adhesion_initiale.value,
                "Frais d'adhésion initiale",
                get_settings().default_adhesion_fcfa,
                None,
            ),
            (
                ParametrePaiementCode.cotisation_mensuelle.value,
                "Cotisation mensuelle standard",
                get_settings().default_cotisation_mensuelle_fcfa,
                None,
            ),
            (
                ParametrePaiementCode.regle_date_premiere_cotisation.value,
                "Règle première cotisation (jour_15 = validé avant le 15 → mois courant ; sinon mois suivant)",
                None,
                "jour_15",
            ),
        ]
        for code, libelle, montant, val_txt in codes_a_seeder:
            existing = await self.repo.get_active_for_code_at(code, today)
            if not existing:
                await self.repo.create(
                    ParametrePaiement(
                        code=code,
                        libelle=libelle,
                        montant_fcfa=montant,
                        valeur_texte=val_txt,
                        date_effet=today,
                    )
                )
        await self.session.commit()


class CotisationsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CotisationMensuelleRepository(session)
        self.adhesions_repo = AdhesionRepository(session)
        self.parametres = ParametresPaiementService(session)

    async def get_mois_courant(self) -> tuple[int, int]:
        today = date.today()
        return (today.year, today.month)

    async def creer_cotisation(
        self,
        adhesion_id: uuid.UUID,
        annee: int,
        mois: int,
        *,
        montant_override: int | None = None,
    ) -> CotisationMensuelle:
        existing = await self.repo.get_for_adherent_mois(adhesion_id, annee, mois)
        if existing:
            return existing
        montant = montant_override
        if montant is None:
            reference_date = date(annee, mois, 1)
            montant = await self.parametres.get_montant(
                ParametrePaiementCode.cotisation_mensuelle, reference_date
            )
        c = CotisationMensuelle(
            adhesion_id=adhesion_id,
            annee=annee,
            mois=mois,
            montant=montant,
            statut=CotisationStatut.en_attente,
        )
        return await self.repo.create(c)

    async def generer_pour_adherent_suite_validation(
        self, adhesion_id: uuid.UUID, date_validation: date | None = None
    ) -> CotisationMensuelle:
        date_v = date_validation or date.today()
        annee_premier, mois_premier = await self.parametres.determiner_premier_mois_cotisation(
            date_v
        )
        annee_courante, mois_courant = await self.get_mois_courant()
        derniere_annee = annee_courante
        derniere_mois = mois_courant
        if (annee_premier, mois_premier) > (derniere_annee, derniere_mois):
            derniere_annee, derniere_mois = annee_premier, mois_premier
        created: CotisationMensuelle | None = None
        a, m = annee_premier, mois_premier
        while (a, m) <= (derniere_annee, derniere_mois):
            c = await self.creer_cotisation(adhesion_id, a, m)
            created = c
            m += 1
            if m > 12:
                m = 1
                a += 1
        assert created is not None
        return created

    async def generer_tous_les_du_mois(
        self, annee: int, mois: int
    ) -> tuple[int, int]:
        from app.models.enums import AdhesionStatus

        q = select(Adhesion.id).where(Adhesion.statut == AdhesionStatus.validee)
        if hasattr(Adhesion, "deleted_at"):
            q = q.where(Adhesion.deleted_at.is_(None))
        res = await self.session.execute(q)
        adhesion_ids = list(res.scalars().all())
        total = len(adhesion_ids)
        crees = 0
        for aid in adhesion_ids:
            existing = await self.repo.get_for_adherent_mois(aid, annee, mois)
            if existing:
                continue
            await self.creer_cotisation(aid, annee, mois)
            crees += 1
        return total, crees

    async def marquer_echues_du_mois_precedent(self) -> int:
        today = date.today()
        last_day_prev = today.replace(day=1) - (
            __import__("datetime").timedelta(days=1)
        )
        annee = last_day_prev.year
        mois = last_day_prev.month
        ids = await self.repo.list_ids_impayes_mois(
            annee, mois, limit=100_000
        )
        updated = 0
        for cid in ids:
            c = await self.repo.get_by_id(cid)
            if c and c.statut == CotisationStatut.en_attente:
                c.statut = CotisationStatut.echue
                updated += 1
        if updated:
            await self.session.flush()
        return updated

    async def historique_adherent(
        self, adhesion_id: uuid.UUID, limit: int = 24
    ) -> list[CotisationMensuelle]:
        return await self.repo.list_for_adherent(adhesion_id, limit)

    async def get_cotisation_courante(
        self, adhesion_id: uuid.UUID
    ) -> CotisationMensuelle | None:
        annee, mois = await self.get_mois_courant()
        return await self.repo.get_for_adherent_mois(adhesion_id, annee, mois)

    async def rapport_mois(
        self, annee: int, mois: int
    ) -> RapportCotisationMois:
        total = await self.repo.count_for_mois(annee, mois)
        payes = await self.repo.count_for_mois(
            annee, mois, CotisationStatut.payee
        )
        en_attente = await self.repo.count_for_mois(
            annee, mois, CotisationStatut.en_attente
        )
        echues = await self.repo.count_for_mois(
            annee, mois, CotisationStatut.echue
        )
        q = (
            select(
                CotisationMensuelle.statut,
                CotisationMensuelle.montant,
            )
            .where(
                CotisationMensuelle.annee == annee,
                CotisationMensuelle.mois == mois,
            )
        )
        res = await self.session.execute(q)
        rows = res.all()
        montant_total = sum(m for _, m in rows)
        montant_percu = sum(
            m
            for statut, m in rows
            if statut == CotisationStatut.payee
        )
        return RapportCotisationMois(
            annee=annee,
            mois=mois,
            total=total,
            payes=payes,
            en_attente=en_attente,
            echues=echues,
            montant_total=montant_total,
            montant_percu=montant_percu,
        )

    async def paiement_manuel(
        self,
        cotisation_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        note: str | None = None,
        reference_paiement: str | None = None,
    ) -> CotisationMensuelle:
        c = await self.repo.mark_manuel(
            cotisation_id,
            user_id=user_id,
            note=note,
            reference_paiement=reference_paiement,
        )
        if not c:
            raise HTTPException(status_code=404, detail="Cotisation introuvable")
        return c
