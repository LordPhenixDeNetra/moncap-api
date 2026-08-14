from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    normalize_email,
    new_refresh_token,
    verify_password,
)
from app.core.settings import get_settings
from app.models.enums import AppRole
from app.repositories.adhesions import AdhesionRepository
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
        self.adhesions = AdhesionRepository(session)

    async def login(self, *, email: str, password: str, user_agent: str | None, ip: str | None) -> LoginResult:
        norm_email = normalize_email(email)
        provided = password.strip() if password is not None else ""
        if not provided:
            raise HTTPException(status_code=401, detail="Identifiants invalides")

        user = await self.users.get_by_email(norm_email)
        authed = False
        if user is not None:
            if verify_password(provided, user.password_hash):
                authed = True
            else:
                authed = await self._try_militant_initial_password(user=user, provided=provided)
        else:
            user, authed = await self._try_create_login_militant_on_the_fly(
                normalized_email=norm_email, provided=provided
            )

        if not authed or user is None:
            raise HTTPException(status_code=401, detail="Identifiants invalides")

        roles = await self.users.list_roles(user.id)
        if AppRole.militant.value not in roles:
            await self.users.add_role(user_id=user.id, role=AppRole.militant)
            await self.session.flush()
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

    async def _try_militant_initial_password(self, *, user: object, provided: str) -> bool:
        from app.models.user import User as _U

        u: _U = user  # type: ignore[assignment]
        if u.adhesion_id is None:
            return False
        adhesion = await self.adhesions.get_by_id(u.adhesion_id)
        if adhesion is None:
            return False
        candidate = self._initial_password_for(adhesion)
        if candidate and candidate == provided:
            u.password_hash = hash_password(provided)
            await self.session.flush()
            return True
        return False

    async def _try_create_login_militant_on_the_fly(
        self,
        *,
        normalized_email: str,
        provided: str,
    ) -> tuple[object | None, bool]:
        from app.models.user import User as _U

        adhesion = await self.adhesions.get_validated_by_email(normalized_email)
        if adhesion is None:
            return None, False
        candidate = self._initial_password_for(adhesion)
        if not candidate or candidate != provided:
            return None, False
        existing = await self.users.get_by_email(normalized_email)
        if existing is None:
            user: _U = await self.users.create_user(
                email=normalized_email,
                password_hash=hash_password(provided),
                nom=adhesion.nom,
                prenom=adhesion.prenom,
            )
            user.adhesion_id = adhesion.id
            await self.session.flush()
            await self.users.add_role(user_id=user.id, role=AppRole.militant)
            await self.session.flush()
        else:
            user = existing
            if existing.adhesion_id is None:
                existing.adhesion_id = adhesion.id
                existing.password_hash = hash_password(provided)
                await self.session.flush()
            elif not verify_password(provided, existing.password_hash):
                existing.password_hash = hash_password(provided)
                await self.session.flush()
        return user, True

    @staticmethod
    def _initial_password_for(adhesion) -> str | None:
        if getattr(adhesion, "carte_pastef", None):
            v = str(adhesion.carte_pastef).strip()
            if v:
                return v
        if getattr(adhesion, "cni", None):
            v = str(adhesion.cni).strip()
            if v:
                return v
        return None
