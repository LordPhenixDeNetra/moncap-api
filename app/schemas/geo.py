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


class RegionsResponse(BaseModel):
    data: list[RegionOut]


class DepartementsResponse(BaseModel):
    data: list[DepartementOut]


class CommunesResponse(BaseModel):
    data: list[CommuneOut]
