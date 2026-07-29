from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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
