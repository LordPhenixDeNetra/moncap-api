from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, normalize_email
from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus, AppRole
from app.repositories.adhesions import AdhesionRepository
from app.repositories.users import UserRepository


@dataclass(frozen=True)
class MilitantAccountCreated:
    user_id: uuid.UUID
    email: str
    temporary_password: str
    already_exists: bool = False


class MemberAccountService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.adhesions = AdhesionRepository(session)

    @staticmethod
    def _build_initial_password(adhesion: Adhesion) -> str:
        if adhesion.carte_pastef and adhesion.carte_pastef.strip():
            return adhesion.carte_pastef.strip()
        if adhesion.cni and adhesion.cni.strip():
            return adhesion.cni.strip()
        return str(uuid.uuid4())

    async def ensure_militant_account_for(self, *, adhesion_id: uuid.UUID) -> MilitantAccountCreated:
        adhesion = await self.adhesions.get_by_id_for_update(adhesion_id)
        if not adhesion:
            raise HTTPException(status_code=404, detail="Adhésion introuvable")
        if adhesion.statut != AdhesionStatus.validee:
            raise HTTPException(
                status_code=400,
                detail="Le compte militant ne peut être créé que pour une adhésion validée",
            )

        norm_email = normalize_email(adhesion.email)
        user = await self.users.get_by_email(norm_email)

        if user is not None:
            user.nom = adhesion.nom
            user.prenom = adhesion.prenom
            if user.adhesion_id is None:
                user.adhesion_id = adhesion.id
            await self._ensure_roles(user.id, [AppRole.militant])
            await self.session.flush()
            return MilitantAccountCreated(
                user_id=user.id,
                email=user.email,
                temporary_password="",
                already_exists=True,
            )

        initial_password = self._build_initial_password(adhesion)
        password_hash = hash_password(initial_password)
        user = await self.users.create_user(
            email=norm_email,
            password_hash=password_hash,
            nom=adhesion.nom,
            prenom=adhesion.prenom,
        )
        user.adhesion_id = adhesion.id
        await self.session.flush()
        await self.users.add_role(user_id=user.id, role=AppRole.militant)
        await self.session.flush()
        return MilitantAccountCreated(
            user_id=user.id,
            email=user.email,
            temporary_password=initial_password,
            already_exists=False,
        )

    async def _ensure_roles(self, user_id: uuid.UUID, roles: list[AppRole]) -> None:
        existing = {AppRole(r) if isinstance(r, AppRole) else AppRole(str(r)) for r in await self.users.list_roles(user_id)}
        missing = [r for r in roles if r not in existing]
        for role in missing:
            await self.users.add_role(user_id=user_id, role=role)
