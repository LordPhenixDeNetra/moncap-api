from __future__ import annotations

import uuid

from sqlalchemy import select
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
        res = await self.session.execute(select(User).where(User.id == user_id))
        return res.scalar_one_or_none()

    async def list_roles(self, user_id: uuid.UUID) -> list[str]:
        res = await self.session.execute(select(UserRole.role).where(UserRole.user_id == user_id))
        return [r.value if isinstance(r, AppRole) else str(r) for (r,) in res.all()]

    async def create_user(self, *, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def add_role(self, *, user_id: uuid.UUID, role: AppRole) -> None:
        self.session.add(UserRole(user_id=user_id, role=role))
        await self.session.flush()

