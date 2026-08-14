from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenData(BaseModel):
    access_token: str = Field(alias="accessToken")

class LoginResponse(BaseModel):
    data: TokenData


class MilitantProfileLink(BaseModel):
    adhesion_id: uuid.UUID | None = None
    nom: str | None = None
    prenom: str | None = None
    cni: str | None = None
    carte_pastef: str | None = None
    commissariat: str | None = None
    commissariat_scientifique_principal: str | None = None
    commissariat_scientifique_secondaire: str | None = None
    profile_photo_url: str | None = None
    photo_url: str | None = None
    tel_mobile: str | None = None


class MeData(BaseModel):
    id: uuid.UUID
    email: EmailStr
    roles: list[str]
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")
    militant: MilitantProfileLink | None = None


class MeResponse(BaseModel):
    data: MeData
