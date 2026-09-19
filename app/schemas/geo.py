from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class RegionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nom: str


class DepartementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    region_id: uuid.UUID
    nom: str


class CommuneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    departement_id: uuid.UUID
    nom: str


class PaysOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    nom: str
    continent: str


class PaysResponse(BaseModel):
    data: list[PaysOut]


class PaysOutResponse(BaseModel):
    data: PaysOut


class RegionsResponse(BaseModel):
    data: list[RegionOut]


class RegionOutResponse(BaseModel):
    data: RegionOut


class DepartementsResponse(BaseModel):
    data: list[DepartementOut]


class DepartementOutResponse(BaseModel):
    data: DepartementOut


class CommunesResponse(BaseModel):
    data: list[CommuneOut]


class CommuneOutResponse(BaseModel):
    data: CommuneOut
