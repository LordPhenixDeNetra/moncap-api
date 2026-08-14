from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_sessionmaker
from app.models.adhesion import Adhesion
from app.models.article import Article
from app.models.enums import AdhesionStatus
from app.models.user import User
from app.services.members import MemberAccountService, MilitantAccountCreated


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


SAMPLE_TITLES = [
    "Mon parcours militant et pourquoi je soutiens PASTEF",
    "Compte-rendu de la réunion de mon commissariat",
    "Réflexions sur l’engagement citoyen au Sénégal",
    "Les actions concrètes menées dans ma région",
    "Comment construire ensemble le Sénégal que nous voulons",
    "Témoignage : pourquoi j’ai décidé d’adhérer à PASTEF",
    "Mobilisation jeunesse : enjeux et perspectives",
    "Diaspora : organiser la solidarité avec le Sénégal",
    "Commissariat scientifique : nos propositions",
    "Débat démocratique : place aux idées, pas aux égos",
    "Militantisme de terrain : les bonnes pratiques",
    "Annonce : journée citoyenne ce samedi",
]


SAMPLE_BODY_TEMPLATE = """\
Cher(e)s camarades,

Je me présente : {prenom} {nom}, militant(e) du commissariat « {commissariat} » {diaspora_clause}.

{intro}

Voici quelques points que je souhaite partager avec vous :

1. **Engagement** : Nous avons la responsabilité de faire vivre notre mouvement dans nos communes et régions.
2. **Mobilisation** : La réussite passera d’abord par l’adhésion de masse et la présence sur le terrain.
3. **Actions** : Les prochaines semaines seront l’occasion de multiplier les réunions, les porte-à-porte et les rencontres citoyennes.

{conclusion}

À très bientôt pour construire ensemble le Sénégal que nous voulons.
— {prenom} {nom}
"""


INTRO_OPTIONS = [
    "Ces derniers mois, j’ai parcouru ma commune pour échanger avec les citoyens. Leur diagnostic est clair : ils veulent du changement, et ils le veulent maintenant.",
    "Je crois profondément que notre génération a les clés pour transformer le Sénégal. Ce billet est une invitation à agir ensemble.",
    "Lors de la dernière réunion de commissariat, plusieurs idées sont ressorties. Je tenais à les mettre par écrit pour nourrir notre réflexion collective.",
    "La diaspora a un rôle central à jouer. Voici comment nous pouvons nous organiser pour peser de tout notre poids.",
    "La mobilisation commence par l’écoute. J’ai rencontré plusieurs dizaines de familles ces semaines-ci. Voici ce qui ressort de mes échanges.",
]

CONCLUSION_OPTIONS = [
    "Je vous invite à partager ce billet, à le commenter et à me rejoindre dans les actions à venir.",
    "Merci pour votre lecture. N’hésitez pas à proposer vos propres idées en commentaire, nous en avons besoin !",
    "Chaque petit geste compte. Continuons d’avancer main dans la main, avec patience et détermination.",
    "Ensemble, faisons entendre la voix des citoyens, de Dakar à Tambacounda, de Paris à New York.",
    "La route est longue, mais la direction est la bonne. Soyons nombreux, soyons déterminés, soyons solidaires.",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_body(adhesion: Adhesion) -> str:
    diaspora_clause = "(diaspora)" if adhesion.est_diaspora else ""
    return SAMPLE_BODY_TEMPLATE.format(
        nom=adhesion.nom,
        prenom=adhesion.prenom,
        commissariat=adhesion.commissariat or "Commissariat général",
        diaspora_clause=diaspora_clause,
        intro=random.choice(INTRO_OPTIONS),
        conclusion=random.choice(CONCLUSION_OPTIONS),
    )


def _build_summary(body: str) -> str:
    clean = body.replace("\n", " ")
    if len(clean) <= 250:
        return clean
    return clean[:247] + "..."


def _tags_for(adhesion: Adhesion) -> list[str]:
    tags: list[str] = []
    tags.append(adhesion.commissariat or "general")
    if adhesion.est_diaspora:
        tags.append("diaspora")
    if adhesion.niveau_etude:
        tags.append(adhesion.niveau_etude)
    tags.append("engagement")
    if adhesion.commissariat_scientifique_principal:
        tags.append(adhesion.commissariat_scientifique_principal)
    return [t for t in list(dict.fromkeys(tags)) if t][:6]


def _build_article(adhesion: Adhesion, user_id, status: str, order: int) -> Article:
    title = f"{random.choice(SAMPLE_TITLES)} · #{order}"
    body = _build_body(adhesion)
    summary = _build_summary(body)
    tags = json.dumps(_tags_for(adhesion), ensure_ascii=False)
    article = Article(
        title=title,
        summary=summary,
        body=body,
        cover_url=None,
        status=status,
        commissariat=adhesion.commissariat,
        tags=tags,
        author_id=user_id,
        view_count=random.randint(3, 120),
        likes_count=0,
        comments_count=0,
        published_at=now_utc() if status == "published" else None,
        deleted_at=None,
    )
    return article


async def _list_validated_adhesions_without_account(
    session: AsyncSession,
    *,
    limit: int | None,
) -> list[Adhesion]:
    status_value = AdhesionStatus.validee.value if hasattr(AdhesionStatus.validee, "value") else AdhesionStatus.validee
    no_account = ~exists(1).where(User.adhesion_id == Adhesion.id)
    qy = (
        select(Adhesion)
        .where(
            and_(
                Adhesion.statut == status_value,
                Adhesion.deleted_at.is_(None),
                no_account,
            )
        )
        .options(selectinload(Adhesion.user_account))
        .order_by(Adhesion.created_at.asc())
    )
    if limit:
        qy = qy.limit(limit)
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


async def _count_author_articles(session: AsyncSession, user_ids: Iterable) -> dict:
    ids = list(user_ids)
    if not ids:
        return {}
    qy = (
        select(Article.author_id, func.count(Article.id).label("cnt"))
        .where(Article.author_id.in_(ids))
        .where(Article.deleted_at.is_(None))
        .group_by(Article.author_id)
    )
    res = await session.execute(qy)
    return {row.author_id: int(row.cnt) for row in res.all()}


async def seed_militants_and_articles(
    *,
    limit_militants: int | None,
    articles_per_militant: int,
    force_status: str,
    dry_run: bool,
):
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        adhesions = await _list_validated_adhesions_without_account(session, limit=limit_militants)
        print(f"Adhésions validées SANS compte militant : {len(adhesions)}")

        if dry_run:
            for a in adhesions:
                print(f"  → créer compte pour {a.nom} {a.prenom} <{a.email}> (statut={a.statut})")
            print(f"[DRY-RUN] {len(adhesions)} comptes à créer, {articles_per_militant} articles/militant")
            return

        svc = MemberAccountService(session)
        created: list[tuple[MilitantAccountCreated, Adhesion]] = []

        try:
            for a in adhesions:
                res = await svc.ensure_militant_account_for(adhesion_id=a.id)
                if not res.already_exists:
                    created.append((res, a))
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        articles_created = 0
        new_user_ids = [r.user_id for r, _ in created]
        existing_counts = await _count_author_articles(session, new_user_ids)

        try:
            for (res, adhesion), user_id in zip(created, new_user_ids):
                existing = existing_counts.get(user_id, 0)
                for i in range(articles_per_militant):
                    article = _build_article(
                        adhesion,
                        user_id=user_id,
                        status=force_status,
                        order=existing + i + 1,
                    )
                    session.add(article)
                    articles_created += 1
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    nb_new = len(created)
    print(f"Comptes créés : {nb_new}")
    print(f"Articles créés : {articles_created}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed des comptes militants (adhésions validées) + articles de démonstration rattachés.",
    )
    parser.add_argument(
        "--limit-militants",
        type=int,
        default=None,
        help="Nombre max d'adhésions validées à transformer en comptes (défaut : toutes).",
    )
    parser.add_argument(
        "--articles-per-militant",
        type=int,
        default=1,
        help="Nombre d'articles de démo à créer par compte militant (défaut 1).",
    )
    parser.add_argument(
        "--article-status",
        type=str,
        default="published",
        choices=["draft", "published"],
        help="Statut des articles de démo (défaut published).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Afficher les comptes à créer sans rien modifier en base.",
    )
    args = parser.parse_args()

    if Path(".env").exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(".env"))
        except Exception:
            pass

    asyncio.run(
        seed_militants_and_articles(
            limit_militants=args.limit_militants,
            articles_per_militant=args.articles_per_militant,
            force_status=args.article_status,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
