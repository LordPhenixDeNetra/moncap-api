from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import RefreshTokenSession


class RefreshSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenSession | None:
        res = await self.session.execute(
            select(RefreshTokenSession).where(RefreshTokenSession.token_hash == token_hash)
        )
        return res.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> RefreshTokenSession:
        obj = RefreshTokenSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def revoke(self, session_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshTokenSession)
            .where(RefreshTokenSession.id == session_id, RefreshTokenSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )

    async def mark_rotated(self, session_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshTokenSession)
            .where(RefreshTokenSession.id == session_id, RefreshTokenSession.rotated_at.is_(None))
            .values(rotated_at=datetime.now(timezone.utc))
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshTokenSession)
            .where(RefreshTokenSession.user_id == user_id, RefreshTokenSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )

