from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, UploadFile

from app.core.settings import get_settings
from app.models.article import Article, ArticleAttachment, ArticleComment
from app.repositories.article import (
    ArticleCommentRepository,
    ArticleLikeRepository,
    ArticleRepository,
)
from app.storage.local import LocalStorage


_WORD_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)


def _tokenize_query(q: str | None) -> list[str]:
    if not q:
        return []
    out: list[str] = []
    for t in _WORD_RE.findall(q.lower()):
        if len(t) >= 2 and t not in out:
            out.append(t)
    return list(dict.fromkeys(out))


@dataclass(frozen=True)
class CreateArticleInput:
    title: str
    summary: str | None
    body: str
    status: str
    commissariat: str | None
    tags: list[str] | None
    author_id: uuid.UUID


@dataclass(frozen=True)
class UpdateArticleInput:
    title: str | None
    summary: str | None
    body: str | None
    status: str | None
    commissariat: str | None
    tags: list[str] | None
    remove_attachment_ids: list[uuid.UUID] | None


class ArticleService:
    def __init__(self, session):
        self.session = session
        self.articles = ArticleRepository(session)
        self.likes = ArticleLikeRepository(session)
        self.comments = ArticleCommentRepository(session)
        self.storage = LocalStorage()
        self.settings = get_settings()

    def _parse_tags_as_list(self, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x) for x in value]
        if isinstance(value, str):
            if not value.strip():
                return []
            try:
                return list(json.loads(value))
            except Exception:
                return [value]
        return []

    def _inject_relevance_scores(self, items: list[Article], query: str | None) -> None:
        terms = _tokenize_query(query)
        if not terms or not items:
            return
        for art in items:
            score = 0.0
            title_l = (art.title or "").lower()
            summary_l = (art.summary or "").lower()
            body_l = (art.body or "").lower()
            tags_l = " ".join(self._parse_tags_as_list(art.tags)).lower()
            for t in terms:
                if t in title_l:
                    score += 10.0
                if t in summary_l:
                    score += 5.0
                if t in tags_l:
                    score += 8.0
                if t in body_l:
                    score += 1.0
            if score > 0:
                art.score = round(score, 1)
            else:
                art.score = 0.0


    async def _tags_to_stored(self, tags: list[str] | None) -> str | None:
        if tags is None:
            return None
        return json.dumps(list(tags), ensure_ascii=False)

    async def _check_mime_size(
        self,
        *,
        file: UploadFile,
        allowed_mimes: list[str],
        max_mb: int,
        role: str,
    ) -> None:
        if file.content_type:
            ct = file.content_type.lower()
            if ct not in allowed_mimes:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "INVALID_MIME_TYPE",
                        "message": f"Le type de fichier pour {role} n'est pas autorisé",
                        "details": [{"mime": file.content_type, "allowed": allowed_mimes}],
                    },
                )
        size_limit_bytes = max_mb * 1024 * 1024
        if hasattr(file, "size") and file.size is not None:
            if file.size > size_limit_bytes:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "FILE_TOO_LARGE",
                        "message": f"Le fichier {role} dépasse la taille maximale autorisée ({max_mb} Mo)",
                    },
                )

    async def create_article(
        self,
        *,
        data: CreateArticleInput,
        cover: UploadFile | None,
        attachments: list[UploadFile] | None,
    ) -> Article:
        if data.status == "published":
            # On autorise la publication directe par militant; si on veut modération
            # on pourra transformer "published" en "draft" ici côté service.
            pass

        if len(attachments or []) > self.settings.article_max_attachments:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "TOO_MANY_ATTACHMENTS",
                    "message": "Trop de pièces jointes pour l'article",
                    "details": [
                        {
                            "max": self.settings.article_max_attachments,
                            "count": len(attachments or []),
                        }
                    ],
                },
            )

        if cover is not None:
            await self._check_mime_size(
                file=cover,
                allowed_mimes=self.settings.article_allowed_cover_mimes,
                max_mb=self.settings.article_max_cover_mb,
                role="la couverture",
            )

        for att in attachments or []:
            await self._check_mime_size(
                file=att,
                allowed_mimes=self.settings.article_allowed_attachment_mimes,
                max_mb=self.settings.article_max_attachment_mb,
                role="pièce jointe",
            )

        cover_url: str | None = None
        if cover is not None:
            cover_url = await self.storage.save(file=cover, subdir="articles/covers")

        article = Article(
            title=data.title.strip(),
            summary=(data.summary or "").strip() or None,
            body=data.body,
            cover_url=cover_url,
            status=data.status,
            commissariat=(data.commissariat or "").strip() or None,
            tags=await self._tags_to_stored(data.tags),
            author_id=data.author_id,
            published_at=datetime.utcnow() if data.status == "published" else None,
        )
        article = await self.articles.create(article)

        attachment_rows: list[ArticleAttachment] = []
        for i, att in enumerate(attachments or [], start=1):
            url = await self.storage.save(file=att, subdir=f"articles/{article.id.hex}/attachments")
            filename = (att.filename or "fichier").strip()
            mime = (att.content_type or "application/octet-stream").lower()
            size = 0
            if hasattr(att, "size") and att.size is not None:
                size = int(att.size or 0)
            attachment_rows.append(
                ArticleAttachment(
                    article_id=article.id,
                    file_url=url,
                    filename=filename,
                    mime_type=mime,
                    size_bytes=size,
                    order=i,
                )
            )
        if attachment_rows:
            await self.articles.add_attachments(article.id, attachment_rows)

        await self.session.commit()
        await self.session.refresh(article)
        return article

    async def get_public_detail(self, article_id: uuid.UUID) -> Article:
        article = await self.articles.get_by_id(article_id, include_deleted=False)
        if not article:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        if article.status != "published":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        await self.articles.increment_view_count(article_id)
        await self.session.commit()
        await self.session.refresh(article)
        return article

    async def list_public(
        self,
        *,
        page: int,
        page_size: int,
        commissariat: str | None,
        commissariats: list[str] | None,
        commissariat_contains: str | None,
        author_id: uuid.UUID | None,
        author: str | None,
        query: str | None,
        query_mode: str | None,
        tags_any: list[str] | None,
        tags_all: list[str] | None,
        published_from: datetime | None,
        published_to: datetime | None,
        sort: str,
    ) -> tuple[list[Article], int]:
        allowed_sorts = {"latest", "popular", "oldest", "commented", "relevance", "auto"}
        if sort not in allowed_sorts:
            raise HTTPException(status_code=400, detail={"code": "INVALID_SORT", "message": "Tri invalide"})
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = min(max(page_size, 1), 100)
        items, total = await self.articles.list_public(
            page=page,
            page_size=page_size,
            commissariat=commissariat,
            commissariats=commissariats,
            commissariat_contains=commissariat_contains,
            author_id=author_id,
            author=author,
            query=query,
            query_mode=(query_mode or "auto").lower(),
            tags_any=tags_any,
            tags_all=tags_all,
            published_from=published_from,
            published_to=published_to,
            sort=sort,
        )
        self._inject_relevance_scores(items, query)
        return items, total

    async def list_owner(
        self,
        *,
        author_id: uuid.UUID,
        page: int,
        page_size: int,
        status: str | None,
        include_deleted: bool,
    ) -> tuple[list[Article], int]:
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = min(max(page_size, 1), 100)
        return await self.articles.list_owner(
            author_id=author_id,
            page=page,
            page_size=page_size,
            status=status,
            include_deleted=include_deleted,
        )

    async def get_owned_or_404(self, *, article_id: uuid.UUID, principal_id: uuid.UUID, is_admin: bool) -> Article:
        article = await self.articles.get_by_id(article_id, include_deleted=True)
        if not article:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        if not is_admin and article.author_id != principal_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Accès interdit"})
        return article

    async def get_owner_detail(self, article_id: uuid.UUID, principal_id: uuid.UUID, is_admin: bool) -> Article:
        article = await self.articles.get_by_id(article_id, include_deleted=True)
        if not article:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        if not is_admin and article.author_id != principal_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Accès interdit"})
        return article

    async def update_article(
        self,
        *,
        article_id: uuid.UUID,
        principal_id: uuid.UUID,
        is_admin: bool,
        data: UpdateArticleInput,
        cover: UploadFile | None,
        attachments: list[UploadFile] | None,
    ) -> Article:
        article = await self.get_owned_or_404(
            article_id=article_id, principal_id=principal_id, is_admin=is_admin
        )

        existing_count = await self.articles.count_attachments(article.id)
        remove_count = len(data.remove_attachment_ids or [])
        add_count = len(attachments or [])
        final_count = existing_count - remove_count + add_count
        if final_count > self.settings.article_max_attachments:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "TOO_MANY_ATTACHMENTS",
                    "message": "Trop de pièces jointes pour l'article",
                    "details": [{"max": self.settings.article_max_attachments, "final": final_count}],
                },
            )

        if cover is not None:
            await self._check_mime_size(
                file=cover,
                allowed_mimes=self.settings.article_allowed_cover_mimes,
                max_mb=self.settings.article_max_cover_mb,
                role="la couverture",
            )
        for att in attachments or []:
            await self._check_mime_size(
                file=att,
                allowed_mimes=self.settings.article_allowed_attachment_mimes,
                max_mb=self.settings.article_max_attachment_mb,
                role="pièce jointe",
            )

        values: dict = {}
        if data.title is not None:
            values["title"] = data.title.strip()
        if data.summary is not None:
            values["summary"] = (data.summary or "").strip() or None
        if data.body is not None:
            values["body"] = data.body
        if data.status is not None:
            values["status"] = data.status
            if data.status == "published" and article.published_at is None:
                values["published_at"] = datetime.utcnow()
        if data.commissariat is not None:
            values["commissariat"] = (data.commissariat or "").strip() or None
        if data.tags is not None:
            values["tags"] = await self._tags_to_stored(data.tags)
        if cover is not None:
            values["cover_url"] = await self.storage.save(file=cover, subdir="articles/covers")

        if data.remove_attachment_ids:
            await self.articles.remove_attachment_ids(
                article_id=article.id, attachment_ids=data.remove_attachment_ids
            )

        if attachments:
            current_count = existing_count - remove_count
            new_rows: list[ArticleAttachment] = []
            for i, att in enumerate(attachments, start=1):
                url = await self.storage.save(file=att, subdir=f"articles/{article.id.hex}/attachments")
                filename = (att.filename or "fichier").strip()
                mime = (att.content_type or "application/octet-stream").lower()
                size = 0
                if hasattr(att, "size") and att.size is not None:
                    size = int(att.size or 0)
                new_rows.append(
                    ArticleAttachment(
                        article_id=article.id,
                        file_url=url,
                        filename=filename,
                        mime_type=mime,
                        size_bytes=size,
                        order=current_count + i,
                    )
                )
            await self.articles.add_attachments(article.id, new_rows)

        if values:
            await self.articles.update_fields(article_id=article.id, values=values)

        await self.articles.set_counters(article_id=article.id)
        await self.session.commit()
        updated = await self.articles.get_by_id(article.id, include_deleted=True)
        if not updated:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        return updated

    async def delete_article(self, *, article_id: uuid.UUID, principal_id: uuid.UUID, is_admin: bool) -> None:
        await self.get_owned_or_404(article_id=article_id, principal_id=principal_id, is_admin=is_admin)
        rowcount = await self.articles.soft_delete(article_id=article_id)
        if rowcount == 0:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        await self.session.commit()

    async def toggle_like(self, *, article_id: uuid.UUID, user_id: uuid.UUID) -> tuple[bool, int]:
        article = await self.articles.get_by_id(article_id, include_deleted=False)
        if not article:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        if article.status != "published":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        existing = await self.likes.get(article_id=article_id, user_id=user_id)
        if existing:
            await self.likes.delete(existing)
            liked = False
        else:
            await self.likes.create(article_id=article_id, user_id=user_id)
            liked = True
        await self.articles.set_counters(article_id=article_id)
        await self.session.commit()
        refreshed = await self.articles.get_by_id(article_id, include_deleted=False)
        if not refreshed:
            return liked, 0
        return liked, int(refreshed.likes_count or 0)

    async def has_liked(self, *, article_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        if user_id is None:
            return False
        return await self.likes.get(article_id=article_id, user_id=user_id) is not None

    async def list_comments(
        self,
        *,
        article_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ArticleComment], int]:
        article = await self.articles.get_by_id(article_id, include_deleted=False)
        if not article or article.status != "published":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 200:
            page_size = min(max(page_size, 1), 200)
        return await self.comments.list(article_id=article_id, page=page, page_size=page_size)

    async def create_comment(
        self,
        *,
        article_id: uuid.UUID,
        author_id: uuid.UUID,
        body: str,
        parent_id: uuid.UUID | None,
    ) -> ArticleComment:
        article = await self.articles.get_by_id(article_id, include_deleted=False)
        if not article or article.status != "published":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Article introuvable"})
        if parent_id is not None:
            parent = await self.comments.get_by_id(parent_id)
            if not parent or parent.article_id != article_id:
                raise HTTPException(status_code=400, detail={"code": "INVALID_PARENT_COMMENT", "message": "Commentaire parent invalide"})
        c = ArticleComment(
            article_id=article_id,
            author_id=author_id,
            parent_id=parent_id,
            body=body,
        )
        c = await self.comments.create(c)
        await self.articles.set_counters(article_id=article_id)
        await self.session.commit()
        await self.session.refresh(c)
        return c

    async def update_comment(
        self,
        *,
        comment_id: uuid.UUID,
        principal_id: uuid.UUID,
        is_admin: bool,
        body: str,
    ) -> ArticleComment:
        c = await self.comments.get_by_id(comment_id)
        if not c:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Commentaire introuvable"})
        if not is_admin and c.author_id != principal_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Accès interdit"})
        rc = await self.comments.update_body(comment_id=comment_id, body=body)
        if rc == 0:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Commentaire introuvable"})
        await self.session.commit()
        updated = await self.comments.get_by_id(comment_id)
        if not updated:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Commentaire introuvable"})
        return updated

    async def delete_comment(
        self,
        *,
        comment_id: uuid.UUID,
        principal_id: uuid.UUID,
        is_admin: bool,
    ) -> None:
        c = await self.comments.get_by_id(comment_id)
        if not c:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Commentaire introuvable"})
        if not is_admin and c.author_id != principal_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Accès interdit"})
        rc = await self.comments.soft_delete(comment_id)
        if rc == 0:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Commentaire introuvable"})
        await self.articles.set_counters(article_id=c.article_id)
        await self.session.commit()
