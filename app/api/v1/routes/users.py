from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.db.session import get_db
from app.models.enums import AppRole
from app.schemas.users import (
    UserCreateRequest,
    UserCreateResponse,
    UserDeleteResponse,
    UserListResponse,
    UserSchema,
    UserUpdateRequest,
    UserUpdateResponse,
)
from app.services.users import CreateUserInput, UpdateUserInput, UserService


router = APIRouter(
    prefix="/users",
    dependencies=[Depends(require_roles(AppRole.admin))]
)


def _build_user_schema(user) -> UserSchema:
    return UserSchema(
        id=user.id,
        email=user.email,
        roles=[r.role.value if hasattr(r.role, "value") else str(r.role) for r in user.roles],
        createdAt=user.created_at,
        updatedAt=user.updated_at,
        lastLoginAt=user.last_login_at,
    )


@router.get(
    "",
    response_model=UserListResponse,
    summary="Lister les utilisateurs",
    description="Permet aux administrateurs de lister tous les utilisateurs et leurs rôles.",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
):
    users = await UserService(db).list_users()
    return {"data": [_build_user_schema(u) for u in users]}


@router.post(
    "",
    response_model=UserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un utilisateur",
    description="Permet aux administrateurs de créer un nouvel utilisateur avec ses rôles.",
)
async def create_user(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await UserService(db).create_user(
        CreateUserInput(
            email=payload.email,
            password=payload.password,
            roles=payload.roles,
        )
    )
    return {"data": _build_user_schema(user)}


@router.get(
    "/{user_id}",
    response_model=UserCreateResponse,
    summary="Récupérer un utilisateur",
    description="Permet aux administrateurs de récupérer les informations d'un utilisateur par son ID.",
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    user = await UserService(db).get_user(user_id)
    return {"data": _build_user_schema(user)}


@router.patch(
    "/{user_id}",
    response_model=UserUpdateResponse,
    summary="Mettre à jour un utilisateur",
    description="Permet aux administrateurs de modifier l'email, le mot de passe ou les rôles d'un utilisateur.",
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await UserService(db).update_user(
        user_id,
        UpdateUserInput(
            email=payload.email,
            password=payload.password,
            roles=payload.roles,
        ),
    )
    return {"data": _build_user_schema(user)}


@router.delete(
    "/{user_id}",
    response_model=UserDeleteResponse,
    summary="Supprimer un utilisateur",
    description="Permet aux administrateurs de supprimer définitivement un utilisateur.",
)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await UserService(db).delete_user(user_id)
    return {"data": {"deleted": True}}
