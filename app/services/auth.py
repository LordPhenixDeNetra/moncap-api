from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_refresh_token,
    normalize_email,
    new_refresh_token,
    verify_password,
)
from app.core.settings import get_settings
from app.repositories.sessions import RefreshSessionRepository
from app.repositories.users import UserRepository


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class RefreshResult:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.refresh_sessions = RefreshSessionRepository(session)

    async def login(self, *, email: str, password: str, user_agent: str | None, ip: str | None) -> LoginResult:
        norm_email = normalize_email(email)
        user = await self.users.get_by_email(norm_email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Identifiants invalides")

        roles = await self.users.list_roles(user.id)
        access_token = create_access_token(subject=str(user.id), roles=roles)

        settings = get_settings()
        refresh_token = new_refresh_token()
        token_hash = hash_refresh_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.refresh_token_ttl_seconds)

        await self.refresh_sessions.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        user.last_login_at = datetime.now(timezone.utc)
        await self.session.commit()

        return LoginResult(access_token=access_token, refresh_token=refresh_token)

    async def refresh(self, *, refresh_token: str, user_agent: str | None, ip: str | None) -> RefreshResult:
        settings = get_settings()
        token_hash = hash_refresh_token(refresh_token)
        existing = await self.refresh_sessions.get_by_token_hash(token_hash)
        if not existing:
            raise HTTPException(status_code=401, detail="Refresh token invalide")

        now = datetime.now(timezone.utc)
        if existing.revoked_at is not None or existing.rotated_at is not None:
            await self.refresh_sessions.revoke_all_for_user(existing.user_id)
            await self.session.commit()
            raise HTTPException(status_code=401, detail="Refresh token réutilisé")

        expires_at = existing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= now:
            await self.refresh_sessions.revoke(existing.id)
            await self.session.commit()
            raise HTTPException(status_code=401, detail="Refresh token expiré")

        await self.refresh_sessions.mark_rotated(existing.id)

        new_token = new_refresh_token()
        new_hash = hash_refresh_token(new_token)
        new_expires = now + timedelta(seconds=settings.refresh_token_ttl_seconds)
        await self.refresh_sessions.create(
            user_id=existing.user_id,
            token_hash=new_hash,
            expires_at=new_expires,
            user_agent=user_agent,
            ip=ip,
        )

        roles = await self.users.list_roles(existing.user_id)
        access_token = create_access_token(subject=str(existing.user_id), roles=roles)

        await self.session.commit()
        return RefreshResult(access_token=access_token, refresh_token=new_token)

    async def logout(self, *, refresh_token: str) -> None:
        token_hash = hash_refresh_token(refresh_token)
        existing = await self.refresh_sessions.get_by_token_hash(token_hash)
        if existing:
            await self.refresh_sessions.revoke(existing.id)
            await self.session.commit()
