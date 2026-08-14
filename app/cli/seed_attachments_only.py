from __future__ import annotations

import argparse
import asyncio
import io
import os
import random
import sys
import uuid
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import get_settings
from app.db.session import get_sessionmaker
from app.models.article import Article, ArticleAttachment
from app.storage.local import LocalStorage


if sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf_8", "utf8mb4"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr.encoding.lower().replace("-", "") not in ("utf8", "utf_8", "utf8mb4"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


DEFAULT_IMAGE_MIMES = [
    ("image/jpeg", ".jpg"),
    ("image/png", ".png"),
    ("image/webp", ".webp"),
]

DEFAULT_DOC_MIMES = [
    ("application/pdf", ".pdf"),
    ("application/msword", ".doc"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
]


class InMemoryUploadFile:
    def __init__(self, *, filename: str, content_type: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self._stream = io.BytesIO(self._data)

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size if size > 0 else -1)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)

    async def close(self) -> None:
        self._stream.close()


def _parse_range(s: str) -> tuple[int, int]:
    if s is None:
        raise ValueError("range is None")
    if "," in s:
        a, b = s.split(",", 1)
        lo = int(a.strip())
        hi = int(b.strip())
    else:
        lo = hi = int(str(s).strip())
    if lo < 0 or hi < 0:
        raise ValueError("range values must be >= 0")
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def _build_fake_bytes(*, mime_type: str, size_kb: tuple[int, int]) -> bytes:
    size = random.randint(size_kb[0], size_kb[1])
    target = max(1, size) * 1024
    if mime_type.startswith("image/"):
        header = b"\x89PNG\r\n\x1a\n" if mime_type == "image/png" else (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01" if mime_type == "image/jpeg"
            else b"RIFF----WEBPVP8 "
        )
        remaining = max(0, target - len(header) - 1)
        return header + (b"\x00" * remaining) + b"\n"
    if mime_type == "application/pdf":
        content = f"%PDF-1.4\n% Fake demo seed PDF {os.urandom(8).hex()}\n1 0 obj<< /Type /Catalog >>endobj\n".encode("latin-1", errors="ignore")
        target = max(target, 1024)
        pad = (b"%" + os.urandom(64) + b"\n") * ((target // 64) + 4)
        return content + pad[:target] + b"%%EOF\n"
    if mime_type in ("application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
        header = (
            b"PK\x03\x04\x14\x00\x00\x00\x08\x00----"
            if mime_type.endswith("document")
            else b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        )
        pad = os.urandom(max(target, 2048))
        return header + pad[len(header):]
    return os.urandom(target)


async def _list_all_articles(session: AsyncSession) -> list[Article]:
    qy = (
        select(Article)
        .where(Article.deleted_at.is_(None))
        .options(selectinload(Article.attachments))
        .order_by(Article.created_at.asc())
    )
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


def _attachment_mime_pool(settings) -> list[tuple[str, str]]:
    allowed = settings.article_allowed_attachment_mimes or []
    allowed = [str(x).strip().lower() for x in allowed if str(x).strip()]
    pool: list[tuple[str, str]] = []
    for mime, ext in DEFAULT_IMAGE_MIMES + DEFAULT_DOC_MIMES:
        if not allowed or mime in allowed:
            pool.append((mime, ext))
    if not pool:
        for a in allowed:
            pool.append((a, ".bin"))
    return pool


def _cover_mime_pool(settings) -> list[tuple[str, str]]:
    allowed = settings.article_allowed_cover_mimes or []
    allowed = [str(x).strip().lower() for x in allowed if str(x).strip()]
    pool: list[tuple[str, str]] = []
    for mime, ext in DEFAULT_IMAGE_MIMES:
        if not allowed or mime in allowed:
            pool.append((mime, ext))
    if not pool:
        for a in allowed:
            pool.append((a, ".bin"))
    return pool


def _file_name_for(mime_type: str, ext: str, *, index: int) -> str:
    base_map = {
        "image/jpeg": "photo-engagement",
        "image/png": "illustration-militant",
        "image/webp": "visuel-campagne",
        "application/pdf": "rapport-commissariat",
        "application/msword": "compte-rendu-reunion",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "projet-propositions",
    }
    base = base_map.get(mime_type, "document")
    slug = f"{base}-{index:02d}-{uuid.uuid4().hex[:6]}"
    return f"{slug}{ext}"


async def seed_attachments_only(
    *,
    attachments_per_article: tuple[int, int],
    cover_probability: float,
    dry_run: bool,
    limit_articles: int | None,
):
    settings = get_settings()
    storage = LocalStorage()
    max_attachments = max(0, int(settings.article_max_attachments or 0))
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        articles = await _list_all_articles(session)
        if limit_articles:
            articles = articles[: max(0, limit_articles)]
        print(f"Articles a traiter : {len(articles)}")
        print(f"Max attachments/article (settings) : {max_attachments}")

        mime_pool = _attachment_mime_pool(settings)
        cover_pool = _cover_mime_pool(settings)
        if not mime_pool:
            print("[ERREUR] Aucun MIME autorise pour attachments (verifier ARTICLE_ALLOWED_ATTACHMENT_MIMES).")
            return

        total_attachments_created = 0
        total_covers_created = 0

        for idx, article in enumerate(articles, start=1):
            lo, hi = attachments_per_article
            target_attachments = random.randint(lo, hi)
            if max_attachments > 0:
                existing_count = len(article.attachments or [])
                target_attachments = min(target_attachments, max(0, max_attachments - existing_count))
            target_attachments = max(0, target_attachments)

            need_cover = cover_pool and article.cover_url in (None, "") and random.random() < cover_probability

            if dry_run:
                print(
                    f"  [{idx}] article={article.id} attachments_existants={len(article.attachments or [])} "
                    f"-> ajouter {target_attachments} piece(s) jointe(s)"
                    + (" + couverture" if need_cover else "")
                )
                continue

            new_rows: list[ArticleAttachment] = []
            try:
                existing_count = len(article.attachments or [])
                for i in range(target_attachments):
                    mime_type, ext = random.choice(mime_pool)
                    size_kb_mime = (15, 1200) if mime_type.startswith("image/") else (20, 1500)
                    data = _build_fake_bytes(mime_type=mime_type, size_kb=size_kb_mime)
                    filename = _file_name_for(mime_type, ext, index=i + 1)
                    upload = InMemoryUploadFile(filename=filename, content_type=mime_type, data=data)
                    subdir = f"articles/{article.id.hex}/attachments"
                    try:
                        url = await storage.save(file=upload, subdir=subdir)
                    finally:
                        try:
                            await upload.close()
                        except Exception:
                            pass
                    row = ArticleAttachment(
                        article_id=article.id,
                        file_url=url,
                        filename=filename,
                        mime_type=mime_type,
                        size_bytes=len(data),
                        order=existing_count + i + 1,
                    )
                    session.add(row)
                    new_rows.append(row)
                    total_attachments_created += 1

                if need_cover:
                    mime_type, ext = random.choice(cover_pool)
                    data = _build_fake_bytes(mime_type=mime_type, size_kb=(40, 400))
                    filename = _file_name_for(mime_type, ext, index=0).replace(
                        "photo-engagement", "couverture"
                    ).replace("illustration-militant", "couverture").replace("visuel-campagne", "couverture")
                    upload = InMemoryUploadFile(filename=filename, content_type=mime_type, data=data)
                    subdir = "articles/covers"
                    try:
                        url = await storage.save(file=upload, subdir=subdir)
                    finally:
                        try:
                            await upload.close()
                        except Exception:
                            pass
                    article.cover_url = url
                    total_covers_created += 1

                await session.commit()
            except Exception:
                await session.rollback()
                raise

        if dry_run:
            print(
                f"[DRY-RUN] ~{len(articles)} articles traites, attachments/article=[{attachments_per_article[0]},{attachments_per_article[1]}], "
                f"P(cover)={cover_probability:.0%}"
            )
        else:
            print(f"Pieces jointes (attachments) ajoutees : {total_attachments_created}")
            print(f"Images de couverture (cover_url) ajoutees : {total_covers_created}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed de pieces jointes et couvertures sur les articles existants.",
    )
    parser.add_argument(
        "--attachments-per-article",
        type=str,
        default="1,3",
        help="Nombre de pieces jointes a ajouter par article, 'min,max' (defaut 1,3 ; borne par ARTICLE_MAX_ATTACHMENTS).",
    )
    parser.add_argument(
        "--cover-probability",
        type=float,
        default=0.55,
        help="Probabilite d'ajouter une image de couverture sur les articles qui n'en ont pas (defaut 0.55).",
    )
    parser.add_argument(
        "--limit-articles",
        type=int,
        default=None,
        help="Ne traiter que les N premiers articles (defaut: tous).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne rien modifier, afficher les actions prevues.",
    )
    args = parser.parse_args()

    if Path(".env").exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(".env"))
        except Exception:
            pass

    try:
        att_range = _parse_range(args.attachments_per_article)
    except ValueError as e:
        print(f"[ERREUR] Range invalide : {e}")
        sys.exit(2)

    if not (0.0 <= args.cover_probability <= 1.0):
        print("[ERREUR] --cover-probability doit etre entre 0.0 et 1.0")
        sys.exit(2)

    asyncio.run(
        seed_attachments_only(
            attachments_per_article=att_range,
            cover_probability=float(args.cover_probability),
            dry_run=args.dry_run,
            limit_articles=args.limit_articles,
        )
    )


if __name__ == "__main__":
    main()
