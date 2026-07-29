from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AppRole


class User(BaseModel):
    id: uuid.UUID
    email: EmailStr
    roles: list[str]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_login_at: datetime | None = Field(alias="lastLoginAt")

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    data: list[User]


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    roles: list[AppRole]


class UserCreateResponse(BaseModel):
    data: User
