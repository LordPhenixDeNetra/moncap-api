from __future__ import annotations

import uuid

from pydantic import BaseModel


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
