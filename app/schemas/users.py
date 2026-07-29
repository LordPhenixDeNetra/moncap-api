from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AppRole


class UserSchema(BaseModel):
    id: uuid.UUID
    email: EmailStr
    roles: list[str]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class UserListResponse(BaseModel):
    data: list[UserSchema]


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    roles: list[AppRole]


class UserCreateResponse(BaseModel):
    data: UserSchema


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    roles: list[AppRole] | None = None


class UserUpdateResponse(BaseModel):
    data: UserSchema


class UserDeleteResponse(BaseModel):
    data: dict
