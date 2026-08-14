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
from app.models.adhesion import Adhesion
from app.models.article import Article
from app.models.user import User


async def main() -> int:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        q = (
            select(User, Adhesion)
            .join(Adhesion, Adhesion.id == User.adhesion_id, isouter=True)
        )
        rows = (await session.execute(q)).all()
        hits = []
        for u, adh in rows:
            full = " ".join(
                x for x in [u.prenom, u.nom] if x
            ).strip().lower()
            adh_full = " ".join(
                x for x in [getattr(adh, "prenom", None), getattr(adh, "nom", None)] if x
            ).strip().lower() if adh else ""
            needles = [
                "fatou kine sarr",
                "fatou kine sarr",
                "fatou kine sar",
                "fatou kine sar",
            ]
            def norm(s: str) -> str:
                return s.replace("é", "e").replace("è", "e").replace("ê", "e") \
                    .replace("à", "a").replace("â", "a").replace("ô", "o") \
                    .replace("û", "u").replace("ù", "u").replace("î", "i") \
                    .replace("ï", "i").replace(" ", "")
            match = False
            for nd in needles:
                if norm(nd) in norm(full) or norm(nd) in norm(adh_full):
                    match = True
                    break
            if match:
                hits.append((u, adh))
        if not hits:
            print("AUCUN USER 'Fatou Kiné Sarr' trouvé (recherche large)")
            all_names = []
            for u, adh in rows:
                all_names.append(" ".join(x for x in [u.prenom, u.nom] if x).strip())
            print("Exemples noms users (30 premiers):", all_names[:30])
            return 2
        for u, adh in hits:
            print(f"\n=== USER: id={u.id} email={u.email} nom={u.prenom} {u.nom} adh_id={u.adhesion_id} ===")
            arts = (await session.execute(
                select(Article)
                .where(Article.author_id == u.id, Article.deleted_at.is_(None))
                .order_by(Article.created_at.desc())
            )).scalars().all()
            print(f"Articles (total {len(arts)}), 3 premiers:")
            for i, a in enumerate(arts[:3], 1):
                print(f"  [{i}] id={a.id}  status={a.status}  title={a.title!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
