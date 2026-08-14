from __future__ import annotations

from sqlalchemy import select

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.core.auth import Principal, get_principal
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.adhesions import AdhesionRepository
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth")


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
        max_age=settings.refresh_token_ttl_seconds,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.refresh_cookie_name, path=settings.refresh_cookie_path)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authentification utilisateur",
    description="Permet à un utilisateur de se connecter avec son email et son mot de passe. Retourne un Access Token (JWT) et définit un Refresh Token dans un cookie HttpOnly.",
)
async def login(payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    res = await service.login(
        email=str(payload.email),
        password=payload.password,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, res.refresh_token)
    return {"data": {"accessToken": res.access_token}}


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Rafraîchir le jeton d'accès",
    description="Utilise le Refresh Token stocké dans les cookies pour générer un nouveau Access Token et un nouveau Refresh Token (rotation).",
)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token manquant")
    service = AuthService(db)
    res = await service.refresh(
        refresh_token=token,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, res.refresh_token)
    return {"data": {"accessToken": res.access_token}}


@router.post(
    "/logout",
    summary="Déconnexion",
    description="Révoque le Refresh Token actuel et supprime le cookie de session.",
)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if token:
        await AuthService(db).logout(refresh_token=token)
    _clear_refresh_cookie(response)
    return {"data": {"ok": True}}


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Informations utilisateur actuel",
    description="Retourne les informations de l'utilisateur actuellement authentifié à partir de son Access Token.",
)
async def me(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    user_q = await db.execute(
        select(User)
        .options(selectinload(User.adhesion))
        .where(User.id == principal.user_id)
    )
    user: User | None = user_q.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    militant = None
    adhesion = getattr(user, "adhesion", None)
    if adhesion is None and getattr(user, "adhesion_id", None) is not None:
        adhesion = await AdhesionRepository(db).get_by_id(user.adhesion_id)  # type: ignore[arg-type]
    if adhesion is not None:
        militant = {
            "adhesion_id": adhesion.id,
            "nom": adhesion.nom,
            "prenom": adhesion.prenom,
            "cni": adhesion.cni,
            "carte_pastef": adhesion.carte_pastef,
            "commissariat": adhesion.commissariat,
            "commissariat_scientifique_principal": adhesion.commissariat_scientifique_principal,
            "commissariat_scientifique_secondaire": adhesion.commissariat_scientifique_secondaire,
            "profile_photo_url": adhesion.profile_photo_url,
            "photo_url": adhesion.photo_url,
            "tel_mobile": adhesion.tel_mobile,
        }

    return {
        "data": {
            "id": user.id,
            "email": user.email,
            "roles": principal.roles,
            "lastLoginAt": user.last_login_at,
            "militant": militant,
        }
    }
