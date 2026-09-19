from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_serializer

from app.core.urls import to_absolute_public_url
from app.models.enums import DisabledReason
from app.schemas.geo import CommuneOut, DepartementOut, PaysOut, RegionOut


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

    est_diaspora: bool = False

    region_domicile_id: uuid.UUID | None = None
    departement_domicile_id: uuid.UUID | None = None
    commune_domicile_id: uuid.UUID | None = None
    pays_domicile_id: uuid.UUID | None = None
    ville_domicile: str | None = None

    region_domicile: RegionOut | None = None
    departement_domicile: DepartementOut | None = None
    commune_domicile: CommuneOut | None = None
    pays_domicile: PaysOut | None = None

    region_militantisme_id: uuid.UUID | None = None
    departement_militantisme_id: uuid.UUID | None = None
    commune_militantisme_id: uuid.UUID | None = None
    pays_militantisme_id: uuid.UUID | None = None
    ville_militantisme: str | None = None

    region_militantisme: RegionOut | None = None
    departement_militantisme: DepartementOut | None = None
    commune_militantisme: CommuneOut | None = None
    pays_militantisme: PaysOut | None = None

    @field_serializer("profile_photo_url", "photo_url")
    def _abs_urls(self, v: str | None) -> str | None:
        return to_absolute_public_url(v)


class MeData(BaseModel):
    id: uuid.UUID
    email: EmailStr
    roles: list[str]
    is_active: bool = Field(default=True, alias="isActive")
    disabled_at: datetime | None = Field(default=None, alias="disabledAt")
    disabled_reason_code: DisabledReason | None = Field(default=None, alias="disabledReasonCode")
    disabled_by_user_id: uuid.UUID | None = Field(default=None, alias="disabledByUserId")
    disabled_motif: str | None = Field(default=None, alias="disabledMotif")
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")
    militant: MilitantProfileLink | None = None


class MeResponse(BaseModel):
    data: MeData
