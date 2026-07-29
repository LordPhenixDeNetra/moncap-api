from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, normalize_email
from app.models.enums import AppRole
from app.models.user import User
from app.repositories.users import UserRepository


@dataclass(frozen=True)
class CreateUserInput:
    email: str
    password: str
    roles: list[AppRole]


@dataclass(frozen=True)
class UpdateUserInput:
    email: str | None
    password: str | None
    roles: list[AppRole] | None


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    async def list_users(self) -> list[User]:
        return await self.users.list_all()

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        return user

    async def create_user(self, data: CreateUserInput) -> User:
        email = normalize_email(data.email)

        existing = await self.users.get_by_email(email)
        if existing:
            raise HTTPException(status_code=409, detail="Un utilisateur avec cet e-mail existe déjà")

        if not data.roles:
            raise HTTPException(status_code=400, detail="Au moins un rôle est requis")

        password_hash = hash_password(data.password)
        user = await self.users.create_user(email=email, password_hash=password_hash)

        for role in data.roles:
            await self.users.add_role(user_id=user.id, role=role)

        await self.session.commit()
        return await self.users.get_by_id(user.id)

    async def update_user(self, user_id: uuid.UUID, data: UpdateUserInput) -> User:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")

        if data.email is not None:
            email = normalize_email(data.email)
            existing = await self.users.get_by_email(email)
            if existing and existing.id != user_id:
                raise HTTPException(status_code=409, detail="Un utilisateur avec cet e-mail existe déjà")
            await self.users.update_email(user_id=user_id, email=email)

        if data.password is not None:
            password_hash = hash_password(data.password)
            await self.users.update_password(user_id=user_id, password_hash=password_hash)

        if data.roles is not None:
            if not data.roles:
                raise HTTPException(status_code=400, detail="Au moins un rôle est requis")
            await self.users.replace_roles(user_id=user_id, roles=data.roles)

        await self.session.commit()
        return await self.users.get_by_id(user_id)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        rowcount = await self.users.delete_user(user_id=user_id)
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        await self.session.commit()
