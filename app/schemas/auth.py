from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class TokenData(BaseModel):
    access_token: str = Field(alias="accessToken")

class LoginResponse(BaseModel):
    data: TokenData


class MeData(BaseModel):
    id: uuid.UUID
    email: EmailStr
    roles: list[str]
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")


class MeResponse(BaseModel):
    data: MeData
