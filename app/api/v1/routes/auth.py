from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.settings import get_settings
from app.db.session import get_db
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


@router.post("/login", response_model=LoginResponse)
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


@router.post("/refresh", response_model=LoginResponse)
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


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if token:
        await AuthService(db).logout(refresh_token=token)
    _clear_refresh_cookie(response)
    return {"data": {"ok": True}}


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    user = await UserRepository(db).get_by_id(principal.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return {
        "data": {
            "id": user.id,
            "email": user.email,
            "roles": principal.roles,
            "lastLoginAt": user.last_login_at,
        }
    }
