from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.db.session import get_db
from app.models.enums import AppRole
from app.repositories.users import UserRepository
from app.schemas.users import UserListResponse


router = APIRouter(
    prefix="/users",
    dependencies=[Depends(require_roles(AppRole.admin))]
)


@router.get(
    "",
    response_model=UserListResponse,
    summary="Lister les utilisateurs",
    description="Permet aux administrateurs de lister tous les utilisateurs.",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
):
    users = await UserRepository(db).list_all()
    return {"data": users}
