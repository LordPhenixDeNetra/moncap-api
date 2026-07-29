from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.security import hash_password, normalize_email
from app.db.session import get_db
from app.models.enums import AppRole
from app.repositories.users import UserRepository
from app.schemas.users import (
    UserCreateRequest,
    UserCreateResponse,
    UserDeleteResponse,
    UserListResponse,
    UserSchema,
    UserUpdateRequest,
    UserUpdateResponse,
)


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
    users = await UserRepository(db).list_all()
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
    repo = UserRepository(db)
    email = normalize_email(payload.email)

    existing = await repo.get_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="Un utilisateur avec cet e-mail existe déjà")

    password_hash = hash_password(payload.password)
    user = await repo.create_user(email=email, password_hash=password_hash)

    for role in payload.roles:
        await repo.add_role(user_id=user.id, role=role)

    await db.commit()
    user = await repo.get_by_id(user.id)
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
    user = await UserRepository(db).get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
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
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if payload.email is not None:
        email = normalize_email(payload.email)
        existing = await repo.get_by_email(email)
        if existing and existing.id != user_id:
            raise HTTPException(status_code=409, detail="Un utilisateur avec cet e-mail existe déjà")
        await repo.update_email(user_id=user_id, email=email)

    if payload.password is not None:
        password_hash = hash_password(payload.password)
        await repo.update_password(user_id=user_id, password_hash=password_hash)

    if payload.roles is not None:
        await repo.replace_roles(user_id=user_id, roles=payload.roles)

    await db.commit()
    user = await repo.get_by_id(user_id)
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
    rowcount = await UserRepository(db).delete_user(user_id=user_id)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await db.commit()
    return {"data": {"deleted": True}}
