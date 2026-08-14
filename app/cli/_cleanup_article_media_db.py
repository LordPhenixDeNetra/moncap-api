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

from sqlalchemy import delete, func, select, update

from app.db.session import get_sessionmaker
from app.models.article import Article, ArticleAttachment


async def main() -> int:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        att_before = (await session.execute(select(func.count()).select_from(ArticleAttachment))).scalar_one()
        cover_before = (await session.execute(select(func.count()).select_from(Article).where(Article.cover_url.isnot(None)))).scalar_one()
        print(f"[AVANT] article_attachments rows : {att_before}")
        print(f"[AVANT] articles avec cover_url non NULL : {cover_before}")

        await session.execute(delete(ArticleAttachment))
        await session.execute(update(Article).values(cover_url=None))
        await session.commit()

        att_after = (await session.execute(select(func.count()).select_from(ArticleAttachment))).scalar_one()
        cover_after = (await session.execute(select(func.count()).select_from(Article).where(Article.cover_url.isnot(None)))).scalar_one()
        print(f"[APRES] article_attachments rows : {att_after}")
        print(f"[APRES] articles avec cover_url non NULL : {cover_after}")

    if att_after != 0 or cover_after != 0:
        print("ERREUR nettoyage incomplet")
        return 1
    print("OK: base nettoyée (attachments supprimés, couvertures nullifiées)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
