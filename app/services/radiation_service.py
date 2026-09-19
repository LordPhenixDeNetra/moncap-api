from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import get_settings
from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus, AppRole, DisabledReason
from app.models.paiements import CotisationMensuelle, CotisationStatut
from app.models.user import User, UserRole

# ================================================================
# Rôles EXCLUS de la radiation AUTOMATIQUE (seulement)
# Un admin peut TOUJOURS radier manuellement n'importe qui (avec motif).
# ================================================================
PRIVILEGED_ROLES_AUTO_EXCLUDE: tuple[str, ...] = (
    AppRole.admin.value,
    AppRole.comite_accueil.value,
    AppRole.comite_directoire.value,
    AppRole.coordinateur_commissariat.value,
    AppRole.coordinateur_regional.value,
    AppRole.moderateur.value,
)

STATUTS_IMPAYES = {CotisationStatut.en_attente.value, CotisationStatut.echue.value}
STATUTS_NON_IMPAYES = {CotisationStatut.payee.value, CotisationStatut.annulee.value}


@dataclass(frozen=True)
class MoisImpaye:
    annee: int
    mois: int
    statut: str

    @property
    def ordinal(self) -> int:
        return self.annee * 12 + (self.mois - 1)


@dataclass
class RadiationCandidate:
    adhesion_id: uuid.UUID
    adhesion_nom: str
    adhesion_prenom: str
    email: str
    tel_mobile: str
    user_id: uuid.UUID | None
    streak_mois_impayes: int
    mois_concernes: list[MoisImpaye] = field(default_factory=list)
    premier_mois_impaye: tuple[int, int] | None = None
    dernier_mois_impaye: tuple[int, int] | None = None


class RadiationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Outils: calcul mois courant, conversion ordinal, vérif exclusion role
    # ------------------------------------------------------------------

    @staticmethod
    def _as_of_year_month(*, as_of: datetime | None = None) -> tuple[int, int]:
        ref = as_of.astimezone(timezone.utc) if as_of and as_of.tzinfo else (
            as_of.replace(tzinfo=timezone.utc) if as_of else datetime.now(timezone.utc)
        )
        return ref.year, ref.month

    async def _user_has_privileged_role(self, user_id: uuid.UUID | None) -> bool:
        if user_id is None:
            return False
        stmt = (
            select(1)
            .select_from(UserRole)
            .where(UserRole.user_id == user_id)
            .where(UserRole.role.in_(PRIVILEGED_ROLES_AUTO_EXCLUDE))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.first() is not None

    # ------------------------------------------------------------------
    # Algorithme principal: candidats à la radiation
    # ------------------------------------------------------------------

    async def list_candidates(
        self,
        *,
        as_of: datetime | None = None,
        exclude_privileged_roles: bool = True,
        delai_mois: int | None = None,
        adhesion_ids_filter: Iterable[uuid.UUID] | None = None,
        limit: int | None = None,
    ) -> list[RadiationCandidate]:
        """Retourne la liste des adhésions validees avec N mois impayés CONSÉCUTIFS.

        Définition du "streak" métier : on part du mois as_of et on recule. Le streak
        compte combien de mois d'affilée, EN PARTANT du plus récent, l'adhésion a un
        statut IMPAYE (en_attente / echue). Dès qu'on rencontre un mois payee / annulee
        (ou un mois sans cotisation générée), on casse la chaîne.

        Exemple (as_of = avril 2026) :
          - Fevrier/mars/avril impayés, janvier payé → streak = 3 → CANDIDAT
          - Décembre/janvier/février impayés mais mars payé, avril payé → streak = 0 → PAS candidat
          - 3 mois impayés il y a 2 ans, tout OK récemment → streak = 0 → PAS candidat
        """
        if delai_mois is None:
            delai_mois = self._settings.radiation_delai_mois_impayes_consecutifs
        if delai_mois < 1:
            delai_mois = 1

        as_of_year, as_of_month = self._as_of_year_month(as_of=as_of)
        as_of_ordinal = as_of_year * 12 + (as_of_month - 1)

        # === 1. Récupérer toutes les adhésions STATUT VALIDEE ===
        stmt_adhesions = (
            select(Adhesion)
            .where(Adhesion.statut == AdhesionStatus.validee.value)
            .where(Adhesion.deleted_at.is_(None))
            .options(
                selectinload(Adhesion.user_account),
                selectinload(Adhesion.user_account).selectinload(User.roles),
            )
        )
        if adhesion_ids_filter is not None:
            ids = list(adhesion_ids_filter)
            if ids:
                stmt_adhesions = stmt_adhesions.where(Adhesion.id.in_(ids))
        res = await self.session.execute(stmt_adhesions)
        adhesions: list[Adhesion] = list(res.scalars().unique().all())
        if not adhesions:
            return []

        adhesion_id_to_obj: dict[uuid.UUID, Adhesion] = {a.id: a for a in adhesions}
        adhesion_ids = list(adhesion_id_to_obj.keys())

        # === 2. Récupérer toutes les cotisations pour ces adhésions ===
        stmt_cotis = (
            select(CotisationMensuelle)
            .where(CotisationMensuelle.adhesion_id.in_(adhesion_ids))
            .order_by(
                CotisationMensuelle.adhesion_id,
                CotisationMensuelle.annee,
                CotisationMensuelle.mois,
            )
        )
        res_cotis = await self.session.execute(stmt_cotis)
        all_cotis: list[CotisationMensuelle] = list(res_cotis.scalars().all())

        # Groupement par adhesion_id
        by_adhesion: dict[uuid.UUID, list[CotisationMensuelle]] = {}
        for c in all_cotis:
            by_adhesion.setdefault(c.adhesion_id, []).append(c)

        # === 3. Calculer streak = N derniers mois consécutifs impayés ===
        candidates: list[RadiationCandidate] = []
        for adhesion in adhesions:
            liste = by_adhesion.get(adhesion.id, [])
            nb_cotis_generees = len(liste)
            if nb_cotis_generees <= delai_mois:
                # Moins de (N+1) cotisations générées → nouvelle recrue, protection.
                # On veut laisser au moins 1 mois "offert" + N mois avant de pouvoir radier.
                # Exemple delai=3 → il faut au moins 4 cotisations générées (janvier offert non facturé + 3 mois).
                # Ci-dessus: nb_cotis_generees <= delai_mois → < delai_mois+1
                continue

            # Map ordinal -> statut
            mois_status: dict[int, str] = {}
            for c in liste:
                statut_val = (
                    c.statut.value if isinstance(c.statut, CotisationStatut) else str(c.statut)
                )
                mois_status[c.annee * 12 + (c.mois - 1)] = statut_val

            # Calcul streak EN PARTANT de as_of_ordinal et en reculant
            streak = 0
            mois_concernes_streak: list[MoisImpaye] = []
            cursor = as_of_ordinal
            while cursor in mois_status:
                statut_ici = mois_status[cursor]
                if statut_ici in STATUTS_NON_IMPAYES:
                    break
                # impaye (en_attente / echue / autre non prévu = conservateur)
                streak += 1
                cursor_year = cursor // 12
                cursor_month = (cursor % 12) + 1
                mois_concernes_streak.append(
                    MoisImpaye(annee=cursor_year, mois=cursor_month, statut=statut_ici)
                )
                cursor -= 1

            if streak < delai_mois:
                continue

            # === 4. Exclusion rôles privilégiés (uniquement pour mode auto) ===
            user_id = adhesion.user_account.id if adhesion.user_account else None
            if exclude_privileged_roles and user_id is not None:
                roles = adhesion.user_account.roles
                is_privileged = any(
                    (r.value if isinstance(r.role, AppRole) else str(r.role))
                    in PRIVILEGED_ROLES_AUTO_EXCLUDE
                    for r in roles
                )
                if not is_privileged:
                    # Fallback: verification explicite en base (si eager load non fiable)
                    is_privileged = await self._user_has_privileged_role(user_id)
                if is_privileged:
                    continue

            # mois_concernes_streak a été créé du +récent au +ancien → inverser
            mois_concernes_streak.reverse()
            premier = (
                (mois_concernes_streak[0].annee, mois_concernes_streak[0].mois)
                if mois_concernes_streak
                else None
            )
            dernier = (
                (mois_concernes_streak[-1].annee, mois_concernes_streak[-1].mois)
                if mois_concernes_streak
                else None
            )

            candidates.append(
                RadiationCandidate(
                    adhesion_id=adhesion.id,
                    adhesion_nom=adhesion.nom,
                    adhesion_prenom=adhesion.prenom,
                    email=adhesion.email,
                    tel_mobile=adhesion.tel_mobile,
                    user_id=user_id,
                    streak_mois_impayes=streak,
                    mois_concernes=mois_concernes_streak,
                    premier_mois_impaye=premier,
                    dernier_mois_impaye=dernier,
                )
            )
            if limit and len(candidates) >= limit:
                break

        return candidates

    # ------------------------------------------------------------------
    # Action atomique : RADIER une adhesion (manuel ou auto)
    # ------------------------------------------------------------------

    async def apply_radiation(
        self,
        *,
        adhesion_id: uuid.UUID,
        reason_code: DisabledReason,
        motif: str,
        radie_par_user_id: uuid.UUID | None = None,
    ) -> tuple[Adhesion, User | None]:
        """Radiation atomique : met à jour adhesion ET user dans la même transaction.

        L'appelant est responsable du session.commit() après (pour BackgroundTasks email notamment).
        """
        now = datetime.now(timezone.utc)

        # Charger l'adhésion avec user_account
        q = (
            select(Adhesion)
            .where(Adhesion.id == adhesion_id)
            .where(Adhesion.deleted_at.is_(None))
            .options(selectinload(Adhesion.user_account))
        )
        res = await self.session.execute(q)
        adhesion = res.scalar_one_or_none()
        if adhesion is None:
            raise HTTPException(status_code=404, detail="Adhésion introuvable")

        if adhesion.statut == AdhesionStatus.radiee.value:
            raise HTTPException(status_code=409, detail="Adhésion déjà radiée")

        if adhesion.statut != AdhesionStatus.validee.value and reason_code == DisabledReason.AUTOMATIQUE_3_MOIS:
            raise HTTPException(
                status_code=409,
                detail="Radiation auto réservée aux adhésions validées",
            )

        adhesion.statut = AdhesionStatus.radiee.value
        adhesion.radie_at = now
        adhesion.radie_par_user_id = radie_par_user_id
        adhesion.radiation_reason_code = reason_code
        adhesion.radiation_motif = motif

        user = adhesion.user_account
        if user is not None:
            user.is_active = False
            user.disabled_at = now
            user.disabled_reason_code = reason_code
            user.disabled_by_user_id = radie_par_user_id
            user.disabled_motif = motif

        await self.session.flush()
        return adhesion, user

    # ------------------------------------------------------------------
    # Action atomique : REHABILITER (100% MANUEL ADMIN)
    # ------------------------------------------------------------------

    async def apply_reactivation(
        self,
        *,
        adhesion_id: uuid.UUID,
        motif: str,
        reactiv_par_user_id: uuid.UUID,
    ) -> tuple[Adhesion, User | None]:
        """Réhabilitation manuelle. REMET statut=validee, is_active=true, efface timestamps/reason."""
        q = (
            select(Adhesion)
            .where(Adhesion.id == adhesion_id)
            .where(Adhesion.deleted_at.is_(None))
            .options(selectinload(Adhesion.user_account))
        )
        res = await self.session.execute(q)
        adhesion = res.scalar_one_or_none()
        if adhesion is None:
            raise HTTPException(status_code=404, detail="Adhésion introuvable")

        if adhesion.statut != AdhesionStatus.radiee.value:
            raise HTTPException(status_code=409, detail="Adhésion non radiée")

        adhesion.statut = AdhesionStatus.validee.value
        adhesion.radie_at = None
        adhesion.radie_par_user_id = None
        adhesion.radiation_reason_code = None
        # On conserve radiation_motif avec préfixe pour audit (historique)
        prefixe = f"[REHABILITE {datetime.now(timezone.utc).date().isoformat()} par {reactiv_par_user_id}] Motif: {motif} | Ancien motif radiation: "
        ancien = adhesion.radiation_motif or ""
        adhesion.radiation_motif = prefixe + ancien

        user = adhesion.user_account
        if user is not None:
            user.is_active = True
            user.disabled_at = None
            user.disabled_reason_code = None
            user.disabled_by_user_id = None
            ancien_user_motif = user.disabled_motif or ""
            user.disabled_motif = prefixe + ancien_user_motif

        await self.session.flush()
        return adhesion, user
