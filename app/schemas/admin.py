from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AdhesionStatus


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


class AdminAdhesionItem(BaseModel):
    id: uuid.UUID
    nom: str
    prenom: str
    email: str
    cni: str
    commissariat: str
    statut: AdhesionStatus
    created_at: datetime = Field(alias="createdAt")


class AdminAdhesionListResponse(BaseModel):
    data: list[AdminAdhesionItem]
    meta: PaginationMeta


class AdminUpdateAdhesionRequest(BaseModel):
    statut: AdhesionStatus
    motif_rejet: str | None = Field(default=None, alias="motifRejet")


class AdminUpdateAdhesionResponse(BaseModel):
    data: dict
