from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if Path(".env").exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(".env"))
    except Exception:
        pass

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.article import Article
from app.models.user import User
from sqlalchemy.orm import selectinload


ARTICLE_IDS = [
    "6ef23331-52c7-4aa7-a589-780998e2ecf7",
    "62a12dba-b751-4489-8bbb-50e6a88d3c39",
    "b5c8c468-5e5c-45bf-bd95-32641b080d43",
]


async def main() -> int:
    import uuid as _uuid
    ids = [_uuid.UUID(x) for x in ARTICLE_IDS]
    session_factory = get_sessionmaker()
    async with session_factory() as s:
        rows = (await s.execute(
            select(Article, User)
            .join(User, User.id == Article.author_id)
            .where(Article.id.in_(ids))
            .options(selectinload(Article.attachments))
            .order_by(Article.created_at.asc())
        )).all()
        ok_all = 0
        for a, u in rows:
            atts = [x for x in (a.attachments or []) if str(x.mime_type).lower().startswith("image/")]
            print("=" * 88)
            print(f"Titre: {a.title}")
            print(f"Article ID: {a.id}")
            print(f"Auteur: {u.prenom} {u.nom} ({u.email})")
            print(f"Status: {a.status}")
            print(f"Cover URL : {a.cover_url}  — existe fichier: ", end="")
            from app.core.settings import get_settings
            settings = get_settings()
            root = Path(settings.storage_dir)
            prefix = settings.public_files_path.rstrip("/")
            def path_exists(url: str | None) -> bool:
                if not url:
                    return False
                rel = url[len(prefix)+1:] if url.startswith(prefix + "/") else url
                return (root / rel).is_file()
            print(path_exists(a.cover_url))
            print(f"Attachments images ({len(atts)}) :")
            for i, att in enumerate(atts, 1):
                sz = round(int(att.size_bytes or 0) / 1024, 1) if att.size_bytes else None
                print(f"  [{i}] {att.filename} mime={att.mime_type} size={sz}KB order={att.order}")
                print(f"       url={att.file_url} existe={path_exists(att.file_url)}")
            if a.cover_url and len(atts) >= 2:
                ok_all += 1
        print("=" * 88)
        print(f"Articles avec cover + au moins 2 images attachments : {ok_all}/{len(ids)}")
        return 0 if ok_all == len(ids) else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
