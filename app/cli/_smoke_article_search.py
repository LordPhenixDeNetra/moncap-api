from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

if Path(".env").exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(".env"))
    except Exception:
        pass

from app.db.session import get_sessionmaker
from app.services.article import ArticleService


async def scenario() -> int:
    session_factory = get_sessionmaker()
    async with session_factory() as s:
        svc = ArticleService(s)
        cases = [
            ("Baseline sans filtre", dict(page=1, page_size=5, commissariat=None, commissariats=None, commissariat_contains=None, author_id=None, author=None, query=None, query_mode="auto", tags_any=None, tags_all=None, published_from=None, published_to=None, sort="auto")),
            ("Q multi-mot 'militant sante' AND->fallback OR", dict(page=1, page_size=5, commissariat=None, commissariats=None, commissariat_contains=None, author_id=None, author=None, query="militant sante", query_mode="auto", tags_any=None, tags_all=None, published_from=None, published_to=None, sort="auto")),
            ("Author 'Fatou kine sarr'", dict(page=1, page_size=5, commissariat=None, commissariats=None, commissariat_contains=None, author_id=None, author="Fatou kine sarr", query=None, query_mode="auto", tags_any=None, tags_all=None, published_from=None, published_to=None, sort="auto")),
            ("Commissariats multi 'Dakar-Plateau,Guediawaye'", dict(page=1, page_size=5, commissariat=None, commissariats=["Dakar-Plateau", "Guediawaye"], commissariat_contains=None, author_id=None, author=None, query=None, query_mode="auto", tags_any=None, tags_all=None, published_from=None, published_to=None, sort="latest")),
            ("Tags any 'education,jeunesse' + q 'ecole'", dict(page=1, page_size=5, commissariat=None, commissariats=None, commissariat_contains=None, author_id=None, author=None, query="ecole", query_mode="auto", tags_any=["education", "jeunesse"], tags_all=None, published_from=None, published_to=None, sort="relevance")),
            ("Sort commented", dict(page=1, page_size=5, commissariat=None, commissariats=None, commissariat_contains=None, author_id=None, author=None, query=None, query_mode="auto", tags_any=None, tags_all=None, published_from=None, published_to=None, sort="commented")),
            ("published_from 30 jours", dict(page=1, page_size=5, commissariat=None, commissariats=None, commissariat_contains=None, author_id=None, author=None, query=None, query_mode="auto", tags_any=None, tags_all=None, published_from=datetime.utcnow() - timedelta(days=30), published_to=None, sort="latest")),
        ]
        fails = 0
        for title, kw in cases:
            try:
                items, total = await svc.list_public(**kw)
                scores = [getattr(i, "score", None) for i in items]
                titles = [(i.title, getattr(i, "score", None), (i.author and f"{i.author.prenom} {i.author.nom}")) for i in items[:3]]
                print(f"\n=== {title} -> total={total}, page_items={len(items)}")
                for t, sc, au in titles:
                    sc_str = "" if sc is None else f" score={sc}"
                    print(f"   - {sc_str} {au} : {t}")
            except Exception as e:
                fails += 1
                print(f"\n=== {title} -> ERREUR: {type(e).__name__}: {e}")
        print("\nFails:", fails)
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(scenario()))
