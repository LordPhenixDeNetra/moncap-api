from __future__ import annotations

import json
import re
import uuid
from datetime import datetime

from sqlalchemy import and_, case, cast, delete, desc, func, or_, select, update, String as SAString
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.adhesion import Adhesion
from app.models.article import Article, ArticleAttachment, ArticleComment, ArticleLike
from app.models.user import User


_WORD_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)


def _tokenize_terms(query: str | None) -> list[str]:
    if not query:
        return []
    terms: list[str] = []
    for t in _WORD_RE.findall(query.lower()):
        if len(t) >= 2 and t not in terms:
            terms.append(t)
    return list(dict.fromkeys(terms))


def _split_csv(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


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
        commissariats: list[str] | None,
        commissariat_contains: str | None,
        author_id: uuid.UUID | None,
        author: str | None,
        query: str | None,
        query_mode: str,
        tags_any: list[str] | None,
        tags_all: list[str] | None,
        published_from: datetime | None,
        published_to: datetime | None,
        sort: str,
    ) -> tuple[list[Article], int]:
        where = [Article.status == "published", Article.deleted_at.is_(None)]
        terms = _tokenize_terms(query)
        mode = "and" if (query_mode or "").lower() not in {"or", "and", "auto"} else (query_mode or "and").lower()
        use_author_join = bool(author_id) or bool(author)
        score_expr = None

        if commissariat:
            where.append(Article.commissariat == commissariat)
        if commissariats:
            cleaned = [x for x in commissariats if x]
            if cleaned:
                where.append(Article.commissariat.in_(cleaned))
        if commissariat_contains:
            where.append(Article.commissariat.ilike(f"%{commissariat_contains.strip()}%"))
        if published_from:
            where.append(Article.published_at >= published_from)
        if published_to:
            where.append(Article.published_at <= published_to)
        if author_id:
            where.append(Article.author_id == author_id)

        if tags_any:
            likes = []
            for t in tags_any:
                esc = "%" + t.replace("%", "%%").replace("_", "\\_") + "%"
                likes.append(cast(Article.tags, SAString).ilike(esc))
            where.append(or_(*likes))
        if tags_all:
            for t in tags_all:
                esc = "%" + t.replace("%", "%%").replace("_", "\\_") + "%"
                where.append(cast(Article.tags, SAString).ilike(esc))

        base_from = select(Article)
        if use_author_join:
            base_from = base_from.join(User, User.id == Article.author_id, isouter=False)
        if author:
            author_terms = _tokenize_terms(author)
            if author_terms:
                author_likes = []
                for t in author_terms:
                    like = f"%{t}%"
                    author_likes.append(
                        or_(
                            User.nom.ilike(like),
                            User.prenom.ilike(like),
                            User.email.ilike(like),
                        )
                    )
                where.append(and_(*author_likes))

        if terms:
            all_terms = list(terms)
            title_score = 0
            summary_score = 0
            body_score = 0
            tags_score = 0
            per_term_matches = []
            for t in all_terms:
                like = f"%{t}%"
                a_title = Article.title.ilike(like)
                a_summary = Article.summary.ilike(like)
                a_body = Article.body.ilike(like)
                a_tags = cast(Article.tags, SAString).ilike(like)
                per_term_matches.append(or_(a_title, a_summary, a_body, a_tags))
                title_score = title_score + case((a_title, 1), else_=0)
                summary_score = summary_score + case((a_summary, 1), else_=0)
                body_score = body_score + case((a_body, 1), else_=0)
                tags_score = tags_score + case((a_tags, 1), else_=0)

            if mode == "or":
                where.append(or_(*per_term_matches))
            elif mode == "auto":
                if len(all_terms) <= 1:
                    where.append(or_(*per_term_matches) if per_term_matches else True)
                else:
                    where.append(or_(
                        and_(*per_term_matches),
                        (func.coalesce(title_score, 0) + func.coalesce(summary_score, 0) + func.coalesce(tags_score, 0)) >= 1,
                    ))
            else:  # and
                where.append(and_(*per_term_matches) if per_term_matches else True)
            score_expr = (
                (title_score * 10)
                + (summary_score * 5)
                + (tags_score * 8)
                + (body_score * 1)
            )

        base = base_from.where(and_(*where))
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        if mode == "and" and terms and total == 0 and len(terms) > 1:
            new_where = [w for w in where if True]
            # remplacer la dernière clause AND terms par OR
            last = new_where.pop() if new_where else None
            _ = last
            or_clause = or_(*per_term_matches)
            new_where.append(or_clause)
            base = base_from.where(and_(*new_where))
            count_q2 = select(func.count()).select_from(base.subquery())
            total = (await self.session.execute(count_q2)).scalar_one()

        if sort == "popular":
            order = (desc(Article.likes_count), desc(Article.view_count), desc(Article.published_at))
        elif sort == "oldest":
            order = (Article.published_at.asc(), Article.created_at.asc())
        elif sort == "commented":
            order = (desc(Article.comments_count), desc(Article.likes_count), desc(Article.published_at))
        elif sort == "latest":
            order = (desc(Article.published_at), desc(Article.created_at))
        elif sort == "relevance":
            order = (desc(score_expr if score_expr is not None else 0), desc(Article.published_at), desc(Article.created_at))
        elif terms and sort in ("auto", None, ""):
            order = (desc(score_expr if score_expr is not None else 0), desc(Article.published_at), desc(Article.created_at))
        else:
            order = (desc(Article.published_at), desc(Article.created_at))

        offset = (page - 1) * page_size
        qy = base.order_by(*order).limit(page_size).offset(offset).options(*self._base_loads())
        if use_author_join:
            qy = qy.options(selectinload(Article.author))
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
