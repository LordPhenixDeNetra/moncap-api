from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.enums import AppRole
from app.schemas.article import (
    ArticleCommentOut,
    ArticleCommentsResponse,
    ArticleCreatePayload,
    ArticleListResponse,
    ArticleOut,
    ArticleUpdatePayload,
    CommentCreatePayload,
    CommentUpdatePayload,
    LikeResponse,
)
from app.services.article import ArticleService, CreateArticleInput, UpdateArticleInput


public_router = APIRouter(prefix="/articles", tags=["Articles"])
protected_router = APIRouter(prefix="/articles", tags=["Articles"])


def _to_comment_out(c, principal_id: uuid.UUID | None) -> ArticleCommentOut:
    deleted = c.deleted_at is not None
    body = c.body if not deleted or (principal_id is not None and c.author_id == principal_id) else "[supprimé]"
    return ArticleCommentOut(
        id=c.id,
        article_id=c.article_id,
        author_id=c.author_id,
        parent_id=c.parent_id,
        body=body,
        deleted=deleted,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _is_admin(principal: Principal) -> bool:
    return AppRole.admin.value in principal.roles


# ------------------------------- PUBLIC ----------------------------------- #


@public_router.get("", response_model=ArticleListResponse)
async def list_articles_public(
    page: int = 1,
    page_size: int = 20,
    commissariat: str | None = None,
    author_id: uuid.UUID | None = None,
    q: str | None = None,
    sort: str = "latest",
    db: AsyncSession = Depends(get_db),
):
    items, total = await ArticleService(db).list_public(
        page=page,
        page_size=page_size,
        commissariat=commissariat,
        author_id=author_id,
        query=q,
        sort=sort,
    )
    return ArticleListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ArticleOut.model_validate(it) for it in items],
    )


@public_router.get("/{article_id}", response_model=ArticleOut)
async def get_article_public(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    a = await ArticleService(db).get_public_detail(article_id)
    return ArticleOut.model_validate(a)


@public_router.get("/{article_id}/comments", response_model=ArticleCommentsResponse)
async def list_comments_public(
    article_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    items, total = await ArticleService(db).list_comments(article_id=article_id, page=page, page_size=page_size)
    return ArticleCommentsResponse(
        total=total,
        items=[ArticleCommentOut.model_validate(_to_comment_out(c, None)) for c in items],
    )


# ------------------------------- PROTECTED -------------------------------- #


AUTHORIZED_ROLES = [
    "admin",
    "comite_accueil",
    "comite_directoire",
    "coordinateur_commissariat",
    "coordinateur_regional",
    "militant",
]


def _parse_tags(tags: str | None) -> list[str] | None:
    if tags is None:
        return None
    if tags.strip() == "":
        return []
    try:
        parsed = json.loads(tags)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
        return [tags.strip()]
    except Exception:
        return [t.strip() for t in tags.split(",") if t.strip()]


def _parse_remove_ids(ids: str | None) -> list[uuid.UUID] | None:
    if ids is None or ids.strip() == "":
        return None
    try:
        parsed = json.loads(ids)
        if isinstance(parsed, list):
            return [uuid.UUID(str(x)) for x in parsed]
        return [uuid.UUID(str(ids))]
    except Exception:
        return [uuid.UUID(x.strip()) for x in ids.split(",") if x.strip()]


@protected_router.get(
    "/mine",
    response_model=ArticleListResponse,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def list_my_articles(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    include_deleted: bool = False,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    items, total = await ArticleService(db).list_owner(
        author_id=principal.user_id,
        page=page,
        page_size=page_size,
        status=status,
        include_deleted=include_deleted,
    )
    return ArticleListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ArticleOut.model_validate(it) for it in items],
    )


@protected_router.get(
    "/{article_id}",
    response_model=ArticleOut,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def get_article_owner(
    article_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    a = await ArticleService(db).get_owner_detail(
        article_id=article_id,
        principal_id=principal.user_id,
        is_admin=_is_admin(principal),
    )
    return ArticleOut.model_validate(a)


@protected_router.post(
    "",
    response_model=ArticleOut,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def create_article(
    title: Annotated[str, Form(..., min_length=3, max_length=255)],
    body: Annotated[str, Form(..., min_length=1)],
    summary: Annotated[str | None, Form(max_length=500)] = None,
    status: Annotated[str, Form()] = "draft",
    commissariat: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    cover: Annotated[UploadFile | None, File()] = None,
    attachments: Annotated[list[UploadFile] | None, File()] = None,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    tags_list = _parse_tags(tags)
    payload = ArticleCreatePayload(
        title=title,
        summary=summary or None,
        body=body,
        status=status,
        commissariat=commissariat or None,
        tags=tags_list,
    )
    art = await ArticleService(db).create_article(
        data=CreateArticleInput(
            title=payload.title,
            summary=payload.summary,
            body=payload.body,
            status=payload.status,
            commissariat=payload.commissariat,
            tags=payload.tags,
            author_id=principal.user_id,
        ),
        cover=cover,
        attachments=attachments,
    )
    return ArticleOut.model_validate(art)


@protected_router.patch(
    "/{article_id}",
    response_model=ArticleOut,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def update_article(
    article_id: uuid.UUID,
    title: Annotated[str | None, Form(min_length=3, max_length=255)] = None,
    body: Annotated[str | None, Form(min_length=1)] = None,
    summary: Annotated[str | None, Form(max_length=500)] = None,
    status: Annotated[str | None, Form()] = None,
    commissariat: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    remove_attachment_ids: Annotated[str | None, Form()] = None,
    cover: Annotated[UploadFile | None, File()] = None,
    attachments: Annotated[list[UploadFile] | None, File()] = None,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    tags_list = _parse_tags(tags)
    remove_ids = _parse_remove_ids(remove_attachment_ids)
    payload = ArticleUpdatePayload(
        title=title,
        summary=summary,
        body=body,
        status=status,
        commissariat=commissariat,
        tags=tags_list,
        remove_attachment_ids=remove_ids,
    )
    updated = await ArticleService(db).update_article(
        article_id=article_id,
        principal_id=principal.user_id,
        is_admin=_is_admin(principal),
        data=UpdateArticleInput(
            title=payload.title,
            summary=payload.summary,
            body=payload.body,
            status=payload.status,
            commissariat=payload.commissariat,
            tags=payload.tags,
            remove_attachment_ids=payload.remove_attachment_ids,
        ),
        cover=cover,
        attachments=attachments,
    )
    return ArticleOut.model_validate(updated)


@protected_router.delete(
    "/{article_id}",
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def delete_article(
    article_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    await ArticleService(db).delete_article(
        article_id=article_id,
        principal_id=principal.user_id,
        is_admin=_is_admin(principal),
    )
    return {"data": {"deleted": True}}


@protected_router.post(
    "/{article_id}/like",
    response_model=LikeResponse,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def like_article(
    article_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    liked, count = await ArticleService(db).toggle_like(article_id=article_id, user_id=principal.user_id)
    return LikeResponse(liked=liked, likes_count=count)


@protected_router.delete(
    "/{article_id}/like",
    response_model=LikeResponse,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def unlike_article(
    article_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    liked, count = await ArticleService(db).toggle_like(article_id=article_id, user_id=principal.user_id)
    return LikeResponse(liked=liked, likes_count=count)


@protected_router.get(
    "/{article_id}/like/me",
    response_model=LikeResponse,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def my_like_status(
    article_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    svc = ArticleService(db)
    has_liked = await svc.has_liked(article_id=article_id, user_id=principal.user_id)
    a = await svc.get_public_detail(article_id)
    return LikeResponse(liked=has_liked, likes_count=int(a.likes_count or 0))


@protected_router.post(
    "/{article_id}/comments",
    response_model=ArticleCommentOut,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def create_comment(
    article_id: uuid.UUID,
    payload: CommentCreatePayload,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    c = await ArticleService(db).create_comment(
        article_id=article_id,
        author_id=principal.user_id,
        body=payload.body,
        parent_id=payload.parent_id,
    )
    return _to_comment_out(c, principal.user_id)


@protected_router.patch(
    "/comments/{comment_id}",
    response_model=ArticleCommentOut,
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def update_comment(
    comment_id: uuid.UUID,
    payload: CommentUpdatePayload,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    c = await ArticleService(db).update_comment(
        comment_id=comment_id,
        principal_id=principal.user_id,
        is_admin=_is_admin(principal),
        body=payload.body,
    )
    return _to_comment_out(c, principal.user_id)


@protected_router.delete(
    "/comments/{comment_id}",
    dependencies=[Depends(require_roles(*AUTHORIZED_ROLES))],
)
async def delete_comment(
    comment_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    await ArticleService(db).delete_comment(
        comment_id=comment_id,
        principal_id=principal.user_id,
        is_admin=_is_admin(principal),
    )
    return {"data": {"deleted": True}}
