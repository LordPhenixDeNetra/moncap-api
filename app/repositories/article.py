from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article, ArticleAttachment, ArticleComment, ArticleLike


class ArticleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _base_loads(self):
        return (
            selectinload(Article.attachments),
            selectinload(Article.author),
        )

    async def create(self, article: Article) -> Article:
        self.session.add(article)
        await self.session.flush()
        return article

    async def get_by_id(self, article_id: uuid.UUID, *, include_deleted: bool = False) -> Article | None:
        qy = select(Article).where(Article.id == article_id).options(*self._base_loads())
        if not include_deleted:
            qy = qy.where(Article.deleted_at.is_(None))
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def increment_view_count(self, article_id: uuid.UUID) -> int:
        res = await self.session.execute(
            update(Article)
            .where(Article.id == article_id)
            .where(Article.deleted_at.is_(None))
            .values(view_count=Article.view_count + 1, updated_at=func.now())
        )
        return res.rowcount or 0

    async def list_public(
        self,
        *,
        page: int,
        page_size: int,
        commissariat: str | None,
        author_id: uuid.UUID | None,
        query: str | None,
        sort: str,
    ) -> tuple[list[Article], int]:
        where = [Article.status == "published", Article.deleted_at.is_(None)]
        if commissariat:
            where.append(Article.commissariat == commissariat)
        if author_id:
            where.append(Article.author_id == author_id)
        if query:
            like = f"%{query.strip()}%"
            where.append(
                or_(
                    Article.title.ilike(like),
                    Article.summary.ilike(like),
                    Article.body.ilike(like),
                )
            )

        base = select(Article).where(and_(*where))
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        if sort == "popular":
            order = desc(Article.likes_count), desc(Article.view_count), desc(Article.published_at)
        else:
            order = desc(Article.published_at), desc(Article.created_at)

        offset = (page - 1) * page_size
        qy = base.order_by(*order).limit(page_size).offset(offset).options(*self._base_loads())
        items = list((await self.session.execute(qy)).scalars().all())
        return items, int(total)

    async def list_owner(
        self,
        *,
        author_id: uuid.UUID,
        page: int,
        page_size: int,
        status: str | None,
        include_deleted: bool,
    ) -> tuple[list[Article], int]:
        where = [Article.author_id == author_id]
        if status:
            where.append(Article.status == status)
        if not include_deleted:
            where.append(Article.deleted_at.is_(None))

        base = select(Article).where(and_(*where))
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        offset = (page - 1) * page_size
        qy = base.order_by(desc(Article.updated_at), desc(Article.created_at)).limit(page_size).offset(offset).options(*self._base_loads())
        items = list((await self.session.execute(qy)).scalars().all())
        return items, int(total)

    async def update_fields(self, *, article_id: uuid.UUID, values: dict) -> int:
        if not values:
            return 0
        res = await self.session.execute(
            update(Article)
            .where(Article.id == article_id)
            .where(Article.deleted_at.is_(None))
            .values(**values, updated_at=func.now())
        )
        return res.rowcount or 0

    async def soft_delete(self, *, article_id: uuid.UUID) -> int:
        res = await self.session.execute(
            update(Article)
            .where(Article.id == article_id)
            .where(Article.deleted_at.is_(None))
            .values(deleted_at=func.now(), updated_at=func.now())
        )
        return res.rowcount or 0

    async def add_attachments(self, article_id: uuid.UUID, attachments: list[ArticleAttachment]) -> list[ArticleAttachment]:
        for i, att in enumerate(attachments, start=1):
            att.article_id = article_id
            if att.order is None or att.order == 0:
                att.order = i
        self.session.add_all(attachments)
        await self.session.flush()
        return attachments

    async def remove_attachment_ids(self, *, article_id: uuid.UUID, attachment_ids: list[uuid.UUID]) -> int:
        if not attachment_ids:
            return 0
        res = await self.session.execute(
            delete(ArticleAttachment).where(
                ArticleAttachment.article_id == article_id,
                ArticleAttachment.id.in_(attachment_ids),
            )
        )
        return res.rowcount or 0

    async def count_attachments(self, article_id: uuid.UUID) -> int:
        qy = select(func.count(ArticleAttachment.id)).where(ArticleAttachment.article_id == article_id)
        res = await self.session.execute(qy)
        return int(res.scalar_one())

    async def set_counters(self, *, article_id: uuid.UUID) -> None:
        likes_q = select(func.count(ArticleLike.id)).where(ArticleLike.article_id == article_id)
        comments_q = (
            select(func.count(ArticleComment.id))
            .where(ArticleComment.article_id == article_id)
            .where(ArticleComment.deleted_at.is_(None))
        )
        likes_count = int((await self.session.execute(likes_q)).scalar_one())
        comments_count = int((await self.session.execute(comments_q)).scalar_one())
        await self.update_fields(article_id=article_id, values={
            "likes_count": likes_count,
            "comments_count": comments_count,
        })


class ArticleLikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, *, article_id: uuid.UUID, user_id: uuid.UUID) -> ArticleLike | None:
        qy = select(ArticleLike).where(
            ArticleLike.article_id == article_id,
            ArticleLike.user_id == user_id,
        )
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def create(self, *, article_id: uuid.UUID, user_id: uuid.UUID) -> ArticleLike:
        obj = ArticleLike(article_id=article_id, user_id=user_id)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, like: ArticleLike) -> None:
        await self.session.delete(like)
        await self.session.flush()


class ArticleCommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _author_join(self, qy):
        return qy

    async def get_by_id(self, comment_id: uuid.UUID) -> ArticleComment | None:
        qy = select(ArticleComment).where(ArticleComment.id == comment_id)
        res = await self.session.execute(qy)
        return res.scalar_one_or_none()

    async def create(self, comment: ArticleComment) -> ArticleComment:
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def list(
        self,
        *,
        article_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ArticleComment], int]:
        where = [ArticleComment.article_id == article_id, ArticleComment.deleted_at.is_(None)]
        base = select(ArticleComment).where(and_(*where))
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        offset = (page - 1) * page_size
        qy = base.order_by(desc(ArticleComment.created_at)).limit(page_size).offset(offset)
        items = list((await self.session.execute(qy)).scalars().all())
        return items, int(total)

    async def update_body(self, *, comment_id: uuid.UUID, body: str) -> int:
        res = await self.session.execute(
            update(ArticleComment)
            .where(ArticleComment.id == comment_id)
            .where(ArticleComment.deleted_at.is_(None))
            .values(body=body, updated_at=func.now())
        )
        return res.rowcount or 0

    async def soft_delete(self, comment_id: uuid.UUID) -> int:
        res = await self.session.execute(
            update(ArticleComment)
            .where(ArticleComment.id == comment_id)
            .where(ArticleComment.deleted_at.is_(None))
            .values(deleted_at=func.now(), updated_at=func.now())
        )
        return res.rowcount or 0
