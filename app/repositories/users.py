from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AppRole
from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        res = await self.session.execute(select(User).where(User.email == email))
        return res.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        res = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        return res.scalar_one_or_none()

    async def list_roles(self, user_id: uuid.UUID) -> list[str]:
        res = await self.session.execute(select(UserRole.role).where(UserRole.user_id == user_id))
        return [r.value if isinstance(r, AppRole) else str(r) for (r,) in res.all()]

    async def create_user(self, *, email: str, password_hash: str, nom: str, prenom: str) -> User:
        user = User(email=email, password_hash=password_hash, nom=nom, prenom=prenom)
        self.session.add(user)
        await self.session.flush()
        return user

    async def add_role(self, *, user_id: uuid.UUID, role: AppRole) -> None:
        self.session.add(UserRole(user_id=user_id, role=role))
        await self.session.flush()

    async def replace_roles(self, *, user_id: uuid.UUID, roles: list[AppRole]) -> None:
        await self.session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for role in roles:
            self.session.add(UserRole(user_id=user_id, role=role))
        await self.session.flush()

    async def update_email(self, *, user_id: uuid.UUID, email: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.email = email
            await self.session.flush()

    async def update_password(self, *, user_id: uuid.UUID, password_hash: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.password_hash = password_hash
            await self.session.flush()

    async def update_nom_prenom(self, *, user_id: uuid.UUID, nom: str, prenom: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.nom = nom
            user.prenom = prenom
            await self.session.flush()

    async def delete_user(self, *, user_id: uuid.UUID) -> int:
        res = await self.session.execute(delete(User).where(User.id == user_id))
        return res.rowcount or 0

    async def list_all(self) -> list[User]:
        res = await self.session.execute(
            select(User).options(selectinload(User.roles)).order_by(User.created_at)
        )
        return list(res.scalars().unique().all())
