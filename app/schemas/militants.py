from __future__ import annotations

import uuid

from pydantic import BaseModel, field_serializer

from app.core.urls import to_absolute_public_url
from app.schemas.geo import CommuneOut, DepartementOut, PaysOut, RegionOut


class MilitantsCountData(BaseModel):
    total: int


class MilitantsCountResponse(BaseModel):
    data: MilitantsCountData


class MilitantsStatItem(BaseModel):
    id: uuid.UUID | None = None
    label: str
    count: int


class MilitantsStatsResponse(BaseModel):
    data: list[MilitantsStatItem]


class MilitantsDiasporaData(BaseModel):
    diaspora: int
    local: int


class MilitantsDiasporaResponse(BaseModel):
    data: MilitantsDiasporaData


class MilitantsTimeseriesItem(BaseModel):
    period: str
    count: int


class MilitantsTimeseriesResponse(BaseModel):
    data: list[MilitantsTimeseriesItem]


class MilitantsHierarchyNode(BaseModel):
    id: uuid.UUID
    label: str
    count: int
    children: list["MilitantsHierarchyNode"]


class MilitantsHierarchyResponse(BaseModel):
    data: list[MilitantsHierarchyNode]


class MilitantLookupData(BaseModel):
    id: uuid.UUID
    nom: str
    prenom: str
    email: str
    tel_mobile: str
    cni: str
    carte_pastef: str | None = None
    photo_url: str | None = None
    profile_photo_url: str | None = None
    commissariat: str

    region_domicile_id: uuid.UUID | None = None
    departement_domicile_id: uuid.UUID | None = None
    commune_domicile_id: uuid.UUID | None = None
    pays_domicile_id: uuid.UUID | None = None
    ville_domicile: str | None = None

    region_domicile: RegionOut | None = None
    departement_domicile: DepartementOut | None = None
    commune_domicile: CommuneOut | None = None
    pays_domicile: PaysOut | None = None

    @field_serializer("photo_url", "profile_photo_url")
    def _abs_urls(self, v: str | None) -> str | None:
        return to_absolute_public_url(v)


class MilitantLookupResponse(BaseModel):
    data: MilitantLookupData
