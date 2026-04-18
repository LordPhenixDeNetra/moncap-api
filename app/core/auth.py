from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.repositories.users import UserRepository


class Principal:
    def __init__(self, *, user_id: uuid.UUID, roles: list[str]):
        self.user_id = user_id
        self.roles = roles


async def get_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié")
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

    sub = payload.get("sub")
    roles = payload.get("roles") or []
    try:
        user_id = uuid.UUID(str(sub))
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

    user = await UserRepository(db).get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    if not isinstance(roles, list):
        roles = []
    roles_str = [str(r) for r in roles]
    return Principal(user_id=user_id, roles=roles_str)


def require_roles(*required: str):
    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if required and not any(r in principal.roles for r in required):
            raise HTTPException(status_code=403, detail="Accès interdit")
        return principal

    return _dep

