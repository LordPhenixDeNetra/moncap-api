from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.urls import to_absolute_public_url
from app.models.enums import ArticleStatus


_VALID_STATUSES_ALL = {e.value for e in ArticleStatus}
_VALID_STATUSES_AUTHOR = {ArticleStatus.draft.value, ArticleStatus.waiting_validation.value}


class ArticleAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    article_id: uuid.UUID
    file_url: str
    filename: str
    mime_type: str
    size_bytes: int
    order: int
    created_at: datetime

    @field_serializer("file_url")
    def _abs_file_url(self, v: str | None) -> str | None:
        return to_absolute_public_url(v)


class ArticleAuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    prenom: str
    profile_photo_url: str | None = None

    @field_serializer("profile_photo_url")
    def _abs_profile_photo(self, v: str | None) -> str | None:
        return to_absolute_public_url(v)


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str | None
    body: str
    cover_url: str | None
    status: str
    commissariat: str | None
    tags: list[str] | None = Field(default=None)
    author_id: uuid.UUID
    author: ArticleAuthorOut | None = None
    validated_by_user_id: uuid.UUID | None = None
    validated_by_user: ArticleAuthorOut | None = None
    validated_at: datetime | None = None
    validation_motif: str | None = None
    rejected_by_user_id: uuid.UUID | None = None
    rejected_by_user: ArticleAuthorOut | None = None
    rejected_at: datetime | None = None
    rejected_motif: str | None = None
    closed_by_user: ArticleAuthorOut | None = None
    closed_at: datetime | None = None
    view_count: int
    likes_count: int
    comments_count: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attachments: list[ArticleAttachmentOut] = Field(default_factory=list)
    score: float | None = Field(default=None, description="Score de pertinence (si recherche/q). Remplit seulement avec q.")

    @field_serializer("cover_url")
    def _abs_cover_url(self, v: str | None) -> str | None:
        return to_absolute_public_url(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: Any) -> list[str] | None:
        if v is None or isinstance(v, list):
            return v
        if isinstance(v, str):
            if not v.strip():
                return []
            try:
                import json

                return list(json.loads(v))
            except Exception:
                return [v]
        return None


class ArticleListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ArticleOut]


class ArticleCreatePayload(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    summary: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1)
    status: str = ArticleStatus.draft.value
    commissariat: str | None = None
    tags: list[str] | None = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES_ALL:
            allowed = ", ".join(sorted(_VALID_STATUSES_ALL))
            raise ValueError(f"status invalide. Valeurs autorisées : {allowed}")
        return v


class ArticleUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    summary: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, min_length=1)
    status: str | None = None
    commissariat: str | None = None
    tags: list[str] | None = None
    remove_attachment_ids: list[uuid.UUID] | None = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in _VALID_STATUSES_ALL:
            allowed = ", ".join(sorted(_VALID_STATUSES_ALL))
            raise ValueError(f"status invalide. Valeurs autorisées : {allowed}")
        return v


class ArticleApprovePayload(BaseModel):
    commentaire: str | None = Field(default=None, max_length=2000)


class ArticleRejectPayload(BaseModel):
    motif: str = Field(min_length=5, max_length=2000)


class ArticleChangesRequestedPayload(BaseModel):
    motif: str = Field(min_length=5, max_length=2000)


class ArticleCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    article_id: uuid.UUID
    author_id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str
    deleted: bool
    created_at: datetime
    updated_at: datetime
    author: ArticleAuthorOut | None = None


class ArticleCommentsResponse(BaseModel):
    total: int
    items: list[ArticleCommentOut]


class CommentCreatePayload(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    parent_id: uuid.UUID | None = None


class CommentUpdatePayload(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class LikeResponse(BaseModel):
    liked: bool
    likes_count: int
