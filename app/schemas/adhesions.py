from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AdhesionStatus


class AdhesionCreatedData(BaseModel):
    id: uuid.UUID
    statut: AdhesionStatus
    created_at: datetime = Field(alias="createdAt")


class AdhesionCreatedResponse(BaseModel):
    data: AdhesionCreatedData


class AdhesionPublicItem(BaseModel):
    id: uuid.UUID
    statut: AdhesionStatus
    created_at: datetime = Field(alias="createdAt")
    motif_rejet: str | None = Field(default=None, alias="motifRejet")


class AdhesionPublicListResponse(BaseModel):
    data: list[AdhesionPublicItem]
