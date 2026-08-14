from __future__ import annotations

import argparse
import asyncio
import difflib
import io
import mimetypes
import random
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import httpx

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cli._unsplash_catalog import UNSPLASH_FREE_PHOTOS, build_url
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


@dataclass
class Downloaded:
    data: bytes
    ext: str
    mime_type: str
    filename: str
    source_url: str


class InMemoryUploadFile:
    def __init__(self, *, filename: str, content_type: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._stream = io.BytesIO(data)

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


def _article_keywords(article: Article, idx: int) -> list[str]:
    tags: list[str] = []
    if article.commissariat:
        tags.append(article.commissariat.lower().replace(" ", "-"))
    try:
        import json as _json

        raw_tags = _json.loads(article.tags) if article.tags else []
        for t in raw_tags or []:
            t = str(t).strip()
            if t:
                tags.append(t)
    except Exception:
        pass
    title_words = [w for w in (article.title or "").replace("·", " ").split() if len(w) >= 4]
    random.seed(article.id.hex + str(idx))
    title_pick = random.sample(title_words, k=min(2, len(title_words))) if title_words else []
    tags.extend(title_pick)
    base_pool = [t.lower() for t in tags if t and len(t) >= 2]
    base_pool = list(dict.fromkeys(base_pool))[:3]
    if not base_pool:
        base_pool = [w.lower() for w in (article.title or "").split() if len(w) >= 3]
        base_pool = list(dict.fromkeys(base_pool))[:3]
    return base_pool


def _pick_photos_for(keywords: Sequence[str], *, k: int) -> list[str]:
    kws = [str(x).lower() for x in keywords if str(x).strip()]
    scored: list[tuple[float, int, str]] = []
    for i, (_, tags) in enumerate(UNSPLASH_FREE_PHOTOS):
        score = 0.0
        for kw in kws:
            best = max(
                (difflib.SequenceMatcher(None, kw, t.lower()).ratio() for t in tags),
                default=0.0,
            )
            score += best
        scored.append((score + random.random() * 0.05, i, UNSPLASH_FREE_PHOTOS[i][0]))
    scored.sort(reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for _, _, pid in scored:
        if pid in seen:
            continue
        out.append(pid)
        seen.add(pid)
        if len(out) >= k:
            break
    if len(out) < k:
        fallback = [pid for pid, _ in UNSPLASH_FREE_PHOTOS if pid not in seen]
        random.shuffle(fallback)
        for pid in fallback:
            if len(out) >= k:
                break
            out.append(pid)
    return out


async def _download_from_catalog(
    client: httpx.AsyncClient,
    photo_id: str,
    *,
    width: int,
    height: int,
) -> Downloaded | None:
    url = build_url(photo_id, width=width, height=height)
    try:
        resp = await client.get(
            url,
            timeout=httpx.Timeout(60, connect=20, read=50, write=20, pool=15),
        )
        if resp.status_code != 200:
            return None
        data = resp.content
        if not isinstance(data, (bytes, bytearray)) or len(data) < 2048:
            return None
        ct = (resp.headers.get("Content-Type") or "").lower()
        if ct.startswith("text/"):
            return None
        if ct and ct.startswith("image/"):
            ext_by_mime = mimetypes.guess_extension(ct.split(";", 1)[0]) or ""
        else:
            ext_by_mime = ""
        ext = ext_by_mime if ext_by_mime else ".jpg"
        mime = ct.split(";", 1)[0].strip() if ct else "image/jpeg"
        if not mime.startswith("image/"):
            return None
        fn = f"unsplash-{photo_id.split('-')[-1]}-{uuid.uuid4().hex[:6]}{ext}"
        try:
            final_url = str(resp.url)
        except Exception:
            final_url = url
        return Downloaded(data=bytes(data), ext=ext, mime_type=mime, filename=fn, source_url=final_url)
    except Exception:
        return None


async def _list_all_articles(session: AsyncSession) -> list[Article]:
    qy = (
        select(Article)
        .where(Article.deleted_at.is_(None))
        .options(selectinload(Article.attachments))
        .order_by(Article.created_at.asc())
    )
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


async def _list_articles_by_ids(session: AsyncSession, article_ids: list[str]) -> list[Article]:
    import uuid as _uuid
    parsed: list[object] = []
    for s in article_ids:
        try:
            parsed.append(_uuid.UUID(str(s).strip()))
        except Exception:
            continue
    if not parsed:
        return []
    qy = (
        select(Article)
        .where(Article.id.in_(parsed), Article.deleted_at.is_(None))
        .options(selectinload(Article.attachments))
        .order_by(Article.created_at.asc())
    )
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


async def _list_articles_by_authors(session: AsyncSession, author_ids: list[str]) -> list[Article]:
    import uuid as _uuid
    parsed: list[object] = []
    for s in author_ids:
        try:
            parsed.append(_uuid.UUID(str(s).strip()))
        except Exception:
            continue
    if not parsed:
        return []
    qy = (
        select(Article)
        .where(Article.author_id.in_(parsed), Article.deleted_at.is_(None))
        .options(selectinload(Article.attachments))
        .order_by(Article.created_at.asc())
    )
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


def _safe_delete_attachment_paths(attachments, settings) -> None:
    root = Path(settings.storage_dir)
    prefix = settings.public_files_path.rstrip("/")
    for a in attachments or []:
        url = getattr(a, "file_url", None)
        if not url:
            continue
        rel = url
        if rel.startswith(prefix + "/"):
            rel = rel[len(prefix) + 1:]
        p = root / rel
        try:
            if p.is_file():
                p.unlink(missing_ok=True)
        except Exception:
            pass


def _safe_delete_cover_path(url: str | None, settings) -> None:
    if not url:
        return
    root = Path(settings.storage_dir)
    prefix = settings.public_files_path.rstrip("/")
    rel = url
    if rel.startswith(prefix + "/"):
        rel = rel[len(prefix) + 1:]
    p = root / rel
    try:
        if p.is_file():
            p.unlink(missing_ok=True)
    except Exception:
        pass


async def seed_real_images(
    *,
    images_per_article: tuple[int, int],
    cover_probability: float,
    dry_run: bool,
    limit_articles: int | None,
    cover_size: tuple[int, int],
    attachment_size: tuple[int, int],
    replace_existing_images: bool,
    concurrent_downloads: int,
    article_ids: list[str] | None = None,
    author_ids: list[str] | None = None,
) -> None:
    settings = get_settings()
    storage = LocalStorage()
    max_attachments = max(0, int(settings.article_max_attachments or 0))
    cover_allowed_mimes = {str(x).strip().lower() for x in (settings.article_allowed_cover_mimes or []) if str(x).strip()}
    att_allowed_mimes = {str(x).strip().lower() for x in (settings.article_allowed_attachment_mimes or []) if str(x).strip()}

    session_factory = get_sessionmaker()

    limits = httpx.Limits(
        max_connections=max(1, int(concurrent_downloads)),
        max_keepalive_connections=max(1, int(concurrent_downloads)),
        keepalive_expiry=15,
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8",
        "Accept-Language": "fr,en;q=0.9",
    }

    async with session_factory() as db_session:
        if article_ids:
            articles = await _list_articles_by_ids(db_session, article_ids)
            print(f"Filtre --article-ids : {len(article_ids)} IDs fournis, {len(articles)} articles trouves")
        elif author_ids:
            articles = await _list_articles_by_authors(db_session, author_ids)
            print(f"Filtre --author-ids : {len(author_ids)} auteurs, {len(articles)} articles trouves")
        else:
            articles = await _list_all_articles(db_session)
        if limit_articles:
            articles = articles[: max(0, limit_articles)]
        print(f"Articles a traiter : {len(articles)}")
        print(f"Max attachments/article (settings) : {max_attachments}")

        plan_pick: list[tuple[int, Article, str, int, tuple[int, int]]] = []
        total_att = 0
        total_cov = 0
        for idx, a in enumerate(articles):
            existing = a.attachments or []
            if replace_existing_images:
                target = random.randint(images_per_article[0], images_per_article[1])
                if max_attachments > 0:
                    target = min(target, max_attachments)
            else:
                remaining = 0 if max_attachments <= 0 else max(0, max_attachments - len(existing))
                target = min(remaining, max(0, random.randint(images_per_article[0], images_per_article[1])))
            target = max(0, target)
            need_cover = (
                (replace_existing_images or a.cover_url in (None, ""))
                and random.random() < cover_probability
            )
            kws = _article_keywords(a, 0)
            picks = _pick_photos_for(kws, k=max(target, 1) + (1 if need_cover else 0))
            photo_i = 0
            for i in range(target):
                pid = picks[photo_i % len(picks)]
                photo_i += 1
                plan_pick.append((len(plan_pick), a, pid, i, attachment_size))
                total_att += 1
            if need_cover:
                pid = picks[photo_i % len(picks)]
                photo_i += 1
                plan_pick.append((len(plan_pick), a, pid, -1, cover_size))
                total_cov += 1

        print(f"Telechargements prevus : {total_att} images attachments + {total_cov} couvertures")
        if dry_run:
            for i, a, pid, img_i, (w, h) in plan_pick:
                kind = "COVER" if img_i < 0 else "ATTACHMENT"
                print(f"  [{i}] {kind} article={a.id} photo={pid} {w}x{h}")
            return

        sem = asyncio.Semaphore(max(1, int(concurrent_downloads)))
        _bad_ids: set[str] = set()
        _all_ids: list[str] = [pid for pid, _ in UNSPLASH_FREE_PHOTOS]
        _fallback_rng = random.Random(42)
        _fallback_pool: list[str] = list(_all_ids)
        _fallback_rng.shuffle(_fallback_pool)

        async with httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(90, connect=20),
            headers=headers,
            follow_redirects=True,
            http2=False,
            verify=True,
        ) as http:
            dl_results: list[tuple[int, Downloaded | None, int, int]] = []

            async def _dl_planned(plan_i: int, a: Article, pid: str, img_i: int, size: tuple[int, int]):
                w, h = size
                async with sem:
                    d = await _download_from_catalog(http, pid, width=w, height=h)
                    attempts = 1
                    while d is None and attempts < 8:
                        if pid in _all_ids:
                            _bad_ids.add(pid)
                        if not _fallback_pool:
                            remaining = [p for p in _all_ids if p not in _bad_ids]
                            _fallback_pool.extend(remaining)
                            _fallback_rng.shuffle(_fallback_pool)
                        if not _fallback_pool:
                            break
                        nxt = None
                        while _fallback_pool and nxt is None:
                            cand = _fallback_pool.pop(0)
                            if cand not in _bad_ids and cand != pid:
                                nxt = cand
                        if nxt is None:
                            break
                        pid = nxt
                        d = await _download_from_catalog(http, pid, width=w, height=h)
                        attempts += 1
                dl_results.append((plan_i, d, a.id, img_i))

            aws = [_dl_planned(i, a, pid, img_i, size) for i, a, pid, img_i, size in plan_pick]
            try:
                await asyncio.gather(*aws, return_exceptions=False)
            except Exception as e:
                print(f"[WARN] telechargements (partiel ok) : {e}")

        if _bad_ids:
            print(f"Note: {len(_bad_ids)} photo IDs rejete (404 ou non conformes): {sorted(_bad_ids)[:5]}...")

        per_article_rows: dict[int, list[ArticleAttachment]] = {a.id: [] for a in articles}
        per_article_cover: dict[int, str | None] = {a.id: None for a in articles}

        for plan_i, dl, aid, img_i in dl_results:
            if dl is None:
                continue
            kind = "COVER" if img_i < 0 else "ATTACHMENT"
            mime = dl.mime_type.lower()
            if kind == "COVER":
                if cover_allowed_mimes and mime not in cover_allowed_mimes:
                    continue
            else:
                if att_allowed_mimes and mime not in att_allowed_mimes:
                    continue
            upload = InMemoryUploadFile(
                filename=dl.filename,
                content_type=dl.mime_type,
                data=dl.data,
            )
            try:
                if kind == "COVER":
                    url = await storage.save(file=upload, subdir="articles/covers")
                    per_article_cover[aid] = url
                else:
                    a = next((x for x in articles if x.id == aid), None)
                    if a is None:
                        continue
                    subdir = f"articles/{a.id.hex}/attachments"
                    url = await storage.save(file=upload, subdir=subdir)
                    existing_count = len(a.attachments or []) + len(per_article_rows[aid])
                    row = ArticleAttachment(
                        article_id=aid,
                        file_url=url,
                        filename=dl.filename,
                        mime_type=dl.mime_type,
                        size_bytes=len(dl.data),
                        order=existing_count + 1,
                    )
                    per_article_rows[aid].append(row)
            finally:
                try:
                    await upload.close()
                except Exception:
                    pass

        for article in articles:
            existing_rows = article.attachments or []
            need_del: list[ArticleAttachment] = []
            if replace_existing_images:
                for at in existing_rows:
                    if at.mime_type and str(at.mime_type).lower().startswith("image/"):
                        need_del.append(at)
            if need_del:
                _safe_delete_attachment_paths(need_del, settings)
                ids_to_del = [r.id for r in need_del]
                if ids_to_del:
                    await db_session.execute(
                        delete(ArticleAttachment).where(ArticleAttachment.id.in_(ids_to_del))
                    )
            if replace_existing_images and article.cover_url:
                _safe_delete_cover_path(article.cover_url, settings)
            new_cover = per_article_cover.get(article.id)
            if new_cover:
                article.cover_url = new_cover
            for r in per_article_rows.get(article.id, []):
                db_session.add(r)
        try:
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

        total_attached = sum(len(v) for v in per_article_rows.values())
        total_covers = sum(1 for v in per_article_cover.values() if v)
        print(f"Images (attachments) ajoutees : {total_attached}")
        print(f"Images de couverture ajoutees : {total_covers}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed images REELLES Unsplash (catalog URL direct) sur articles.",
    )
    parser.add_argument("--images-per-article", type=str, default="1,2")
    parser.add_argument("--cover-probability", type=float, default=0.7)
    parser.add_argument("--limit-articles", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cover-size", type=str, default="1200,700")
    parser.add_argument("--attachment-size", type=str, default="900,600")
    parser.add_argument("--replace-existing-images", action="store_true", default=True)
    parser.add_argument("--keep-existing-images", dest="replace_existing_images", action="store_false")
    parser.add_argument("--concurrent-downloads", type=int, default=6)
    parser.add_argument("--article-ids", type=str, default=None, help="Liste d'IDs articles (separes par virgule)")
    parser.add_argument("--author-ids", type=str, default=None, help="Liste d'IDs auteurs (separes par virgule)")
    args = parser.parse_args()

    if Path(".env").exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(".env"))
        except Exception:
            pass

    article_ids: list[str] | None = None
    author_ids: list[str] | None = None
    if args.article_ids:
        article_ids = [x.strip() for x in str(args.article_ids).split(",") if x.strip()]
    if args.author_ids:
        author_ids = [x.strip() for x in str(args.author_ids).split(",") if x.strip()]

    try:
        images_range = _parse_range(args.images_per_article)
        cw, ch = _parse_range(args.cover_size)
        aw, ah = _parse_range(args.attachment_size)
    except ValueError as e:
        print(f"[ERREUR] Range invalide: {e}")
        sys.exit(2)
    if not (0.0 <= args.cover_probability <= 1.0):
        print("[ERREUR] --cover-probability invalide")
        sys.exit(2)

    asyncio.run(
        seed_real_images(
            images_per_article=images_range,
            cover_probability=args.cover_probability,
            dry_run=args.dry_run,
            limit_articles=args.limit_articles,
            cover_size=(cw, ch),
            attachment_size=(aw, ah),
            replace_existing_images=bool(args.replace_existing_images),
            concurrent_downloads=max(1, int(args.concurrent_downloads or 1)),
            article_ids=article_ids,
            author_ids=author_ids,
        )
    )


if __name__ == "__main__":
    main()
