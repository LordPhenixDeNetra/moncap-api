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
from app.models.article import Article, ArticleComment, ArticleLike
from app.models.enums import AdhesionStatus
from app.models.user import User


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
    "Éducation civique : former les citoyens de demain",
    "Santé pour tous : un droit, pas un privilège",
    "Agriculture et souveraineté alimentaire au Sénégal",
    "Numérique et inclusion : ne laisser personne de côté",
    "Jeunes filles et études : levons les obstacles",
    "Transports et infrastructure : les attentes des citoyens",
    "Retour sur la dernière caravane citoyenne",
    "Petit guide pour organiser une réunion de quartier",
    "Pourquoi il faut parler du budget participatif",
    "Les collectivités territoriales : un espace de pouvoir citoyen",
    "Femmes engagées : faire entendre leur voix",
    "Culture et identité : des atouts pour le Sénégal",
    "Entreprenariat jeune : soutenir les initiatives locales",
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
    "Notre commissariat scientifique vient de publier ses propositions. Je vous propose ici un résumé accessible à toutes et tous.",
    "L’année qui s’ouvre sera décisive. Dès maintenant, préparons-nous sur le terrain pour gagner.",
    "Trop de citoyens se sentent abandonnés. Nous avons le devoir d’être présents, d’écouter et de proposer des réponses claires.",
]

CONCLUSION_OPTIONS = [
    "Je vous invite à partager ce billet, à le commenter et à me rejoindre dans les actions à venir.",
    "Merci pour votre lecture. N’hésitez pas à proposer vos propres idées en commentaire, nous en avons besoin !",
    "Chaque petit geste compte. Continuons d’avancer main dans la main, avec patience et détermination.",
    "Ensemble, faisons entendre la voix des citoyens, de Dakar à Tambacounda, de Paris à New York.",
    "La route est longue, mais la direction est la bonne. Soyons nombreux, soyons déterminés, soyons solidaires.",
    "Citoyen après citoyen, famille après famille, nous bâtissons le Sénégal de demain. Ne lâchons rien.",
    "Ce ne sont pas les grands discours qui changeront les choses, mais notre présence et notre organisation. À l’œuvre !",
]


SAMPLE_COMMENT_OPENERS = [
    "Excellent billet, ça va droit au but !",
    "Merci pour ce partage, très inspirant.",
    "Je suis entièrement d’accord avec ton analyse.",
    "Très bonne initiative, continue comme ça !",
    "C’est exactement le message qu’il faut porter.",
    "Beau témoignage, ça fait plaisir à lire.",
    "Ton engagement est contagieux, merci !",
]

SAMPLE_COMMENT_BODIES = [
    "J’espère que ce message sera lu par le plus grand nombre. La mobilisation est la clé.",
    "Dans mon quartier aussi on sent que les citoyens veulent s’engager. Il faut canaliser cette énergie.",
    "Je rejoins ce combat. Quand est-ce qu’on se retrouve sur le terrain ?",
    "La jeunesse senegalaise doit se lever. Merci de donner l’exemple.",
    "Solidarité depuis la diaspora. On est avec vous, de loin mais chaque jour.",
    "On a besoin de plus d’articles comme ça pour nourrir le débat.",
    "Je partage largement autour de moi. Très bonne lecture.",
]

SAMPLE_COMMENT_CLOSINGS = [
    "Encore bravo. À très bientôt sur le terrain.",
    "Continuons d’échanger, les idées se bonifient à plusieurs.",
    "Je reste à disposition pour toute action citoyenne.",
    "On se tient prêt(e). Senegal debout !",
    "Merci encore, et à très vite pour de nouvelles actions.",
]

SAMPLE_REPLY_OPENERS = [
    "Totalement d’accord avec toi.",
    "Tu as raison sur ce point.",
    "C’est exactement ce que je pensais aussi.",
    "Très bon complément, merci.",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


async def _list_active_users(session: AsyncSession) -> list[User]:
    qy = select(User).order_by(User.created_at.asc())
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


async def _load_users_with_adhesions(session: AsyncSession, user_ids: Iterable) -> list[User]:
    ids = list(user_ids)
    if not ids:
        return []
    qy = (
        select(User)
        .where(User.id.in_(ids))
        .options(selectinload(User.adhesion))
        .order_by(User.created_at.asc())
    )
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


def _build_body(adhesion: Adhesion | None, user: User) -> str:
    commissariat = ""
    est_diaspora = False
    niveau_etude = None
    if adhesion is not None:
        commissariat = adhesion.commissariat or ""
        est_diaspora = bool(adhesion.est_diaspora)
        niveau_etude = adhesion.niveau_etude
    if not commissariat:
        commissariat = "Commissariat général"
    diaspora_clause = "(diaspora)" if est_diaspora else ""
    return SAMPLE_BODY_TEMPLATE.format(
        nom=user.nom,
        prenom=user.prenom,
        commissariat=commissariat,
        diaspora_clause=diaspora_clause,
        intro=random.choice(INTRO_OPTIONS),
        conclusion=random.choice(CONCLUSION_OPTIONS),
    )


def _build_summary(body: str) -> str:
    clean = body.replace("\n", " ")
    if len(clean) <= 250:
        return clean
    return clean[:247] + "..."


def _tags_for(adhesion: Adhesion | None) -> list[str]:
    tags: list[str] = []
    if adhesion is not None:
        tags.append(adhesion.commissariat or "general")
        if adhesion.est_diaspora:
            tags.append("diaspora")
        if adhesion.niveau_etude:
            tags.append(adhesion.niveau_etude)
        if adhesion.commissariat_scientifique_principal:
            tags.append(adhesion.commissariat_scientifique_principal)
    tags.append("engagement")
    if not tags:
        tags = ["general", "engagement"]
    return [t for t in list(dict.fromkeys(tags)) if t][:6]


def _build_article(user: User, adhesion: Adhesion | None, status: str, order: int) -> Article:
    title = f"{random.choice(SAMPLE_TITLES)} · #{order}"
    body = _build_body(adhesion, user)
    summary = _build_summary(body)
    tags = json.dumps(_tags_for(adhesion), ensure_ascii=False)
    return Article(
        title=title,
        summary=summary,
        body=body,
        cover_url=None,
        status=status,
        commissariat=adhesion.commissariat if adhesion is not None else None,
        tags=tags,
        author_id=user.id,
        view_count=random.randint(5, 200),
        likes_count=0,
        comments_count=0,
        published_at=now_utc() if status == "published" else None,
        deleted_at=None,
    )


def _generate_comment_body() -> str:
    parts: list[str] = [random.choice(SAMPLE_COMMENT_OPENERS)]
    bodies = random.sample(SAMPLE_COMMENT_BODIES, k=random.randint(1, 2))
    parts.extend(bodies)
    parts.append(random.choice(SAMPLE_COMMENT_CLOSINGS))
    return " ".join(parts)


def _generate_reply_body() -> str:
    return f"{random.choice(SAMPLE_REPLY_OPENERS)} {random.choice(SAMPLE_COMMENT_BODIES)}"


async def _seed_likes_and_comments(
    session: AsyncSession,
    articles: list[Article],
    users: list[User],
    *,
    likes_range: tuple[int, int],
    comments_range: tuple[int, int],
    replies_range: tuple[int, int],
) -> tuple[int, int, int]:
    if not users:
        return 0, 0, 0

    likes_added = 0
    comments_added = 0
    replies_added = 0

    for article in articles:
        existing_like_user_ids = {like.user_id for like in article.likes or [] if like is not None}
        possible_likers = [u for u in users if u.id != article.author_id and u.id not in existing_like_user_ids]
        target_likes = random.randint(likes_range[0], likes_range[1])
        if possible_likers and target_likes > 0:
            pick_count = min(target_likes, len(possible_likers))
            chosen = random.sample(possible_likers, pick_count)
            for u in chosen:
                like = ArticleLike(article_id=article.id, user_id=u.id)
                session.add(like)
                likes_added += 1
            article.likes_count = int(article.likes_count or 0) + pick_count

        existing_comments_n1 = [
            c for c in article.comments or []
            if c is not None and getattr(c, "deleted_at", None) is None and c.parent_id is None
        ]
        target_comments = random.randint(comments_range[0], comments_range[1])
        target_comments = max(0, target_comments - len(existing_comments_n1))
        new_comments_for_article: list[ArticleComment] = []
        if target_comments > 0:
            for _ in range(target_comments):
                author = random.choice(users)
                comment = ArticleComment(
                    article_id=article.id,
                    author_id=author.id,
                    parent_id=None,
                    body=_generate_comment_body(),
                    deleted_at=None,
                )
                session.add(comment)
                new_comments_for_article.append(comment)
                comments_added += 1
            article.comments_count = int(article.comments_count or 0) + len(new_comments_for_article)

        if replies_range[1] > 0 and new_comments_for_article:
            for comment in new_comments_for_article:
                target_replies = random.randint(replies_range[0], replies_range[1])
                reply_candidates = [u for u in users if u.id != comment.author_id]
                if not reply_candidates:
                    continue
                pick = min(target_replies, len(reply_candidates))
                chosen_reply_authors = random.sample(reply_candidates, pick)
                for u in chosen_reply_authors:
                    reply = ArticleComment(
                        article_id=article.id,
                        author_id=u.id,
                        parent_id=comment.id,
                        body=_generate_reply_body(),
                        deleted_at=None,
                    )
                    session.add(reply)
                    replies_added += 1
                    article.comments_count = int(article.comments_count or 0) + 1

    return likes_added, comments_added, replies_added


async def _list_all_articles(session: AsyncSession) -> list[Article]:
    qy = (
        select(Article)
        .where(Article.deleted_at.is_(None))
        .options(
            selectinload(Article.likes),
            selectinload(Article.comments),
        )
        .order_by(Article.created_at.asc())
    )
    res = await session.execute(qy)
    return list(res.scalars().unique().all())


async def seed_articles_only(
    *,
    articles_range_per_user: tuple[int, int],
    likes_range: tuple[int, int],
    comments_range: tuple[int, int],
    replies_range: tuple[int, int],
    dry_run: bool,
    status: str,
    engage_existing: bool,
):
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        all_users = await _list_active_users(session)
        print(f"Utilisateurs en base : {len(all_users)}")
        if not all_users:
            print("[ERREUR] Aucun utilisateur pour creer des articles.")
            return

        user_ids = [u.id for u in all_users]
        existing_counts = await _count_author_articles(session, user_ids)
        users_with_adhesions = await _load_users_with_adhesions(session, user_ids)
        user_by_id = {u.id: u for u in users_with_adhesions}

        new_articles: list[Article] = []
        articles_created = 0

        if dry_run:
            for u in all_users:
                lo, hi = articles_range_per_user
                target = random.randint(lo, hi)
                adhesion_summary = "sans adhesion"
                uh = user_by_id.get(u.id)
                if uh is not None and uh.adhesion is not None:
                    adhesion_summary = f"adhesion={uh.adhesion.commissariat or 'general'}"
                print(f"  -> {u.nom} {u.prenom} <{u.email}> [{adhesion_summary}] : {target} articles a creer")
            articles_created = sum(
                random.randint(articles_range_per_user[0], articles_range_per_user[1])
                for _ in all_users
            )
        else:
            try:
                for u in all_users:
                    lo, hi = articles_range_per_user
                    target = random.randint(lo, hi)
                    existing = existing_counts.get(u.id, 0)
                    uh = user_by_id.get(u.id)
                    adhesion = uh.adhesion if uh is not None else None
                    for i in range(target):
                        article = _build_article(
                            u,
                            adhesion=adhesion,
                            status=status,
                            order=existing + i + 1,
                        )
                        session.add(article)
                        new_articles.append(article)
                        articles_created += 1
                await session.commit()
                for a in new_articles:
                    await session.refresh(a)
            except Exception:
                await session.rollback()
                raise

        articles_to_engage: list[Article] = []
        if dry_run:
            preview_total_q = await session.execute(
                select(func.count(Article.id)).where(Article.deleted_at.is_(None))
            )
            preview_total = int(preview_total_q.scalar_one() or 0)
            if engage_existing:
                preview_total = max(preview_total, preview_total + articles_created)
            else:
                preview_total = articles_created
            print(
                f"[DRY-RUN] Articles a creer : {articles_created} | "
                f"Articles a peupler en likes/comments : ~{preview_total}"
            )
        else:
            if engage_existing:
                articles_to_engage = await _list_all_articles(session)
            else:
                articles_to_engage = new_articles

            try:
                likes_added, comments_added, replies_added = await _seed_likes_and_comments(
                    session,
                    articles_to_engage,
                    all_users,
                    likes_range=likes_range,
                    comments_range=comments_range,
                    replies_range=replies_range,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        if not dry_run:
            print(f"Articles crees : {articles_created}")
            print(
                f"Likes ajoutes : {likes_added} | Commentaires ajoutes : {comments_added} "
                f"(dont {replies_added} reponses)"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed de contenu articles+likes+commentaires pour les utilisateurs existants.",
    )
    parser.add_argument(
        "--articles-per-user",
        type=str,
        default="8,12",
        help="Nombre d'articles a creer par utilisateur, sous la forme 'min,max' (defaut 8,12).",
    )
    parser.add_argument(
        "--likes-per-article",
        type=str,
        default="4,18",
        help="Nombre de likes/article : 'min,max' (defaut 4,18).",
    )
    parser.add_argument(
        "--comments-per-article",
        type=str,
        default="2,8",
        help="Nombre de commentaires/article (niveau 1) : 'min,max' (defaut 2,8).",
    )
    parser.add_argument(
        "--replies-per-comment",
        type=str,
        default="0,3",
        help="Nombre de reponses/commentaire : 'min,max' (defaut 0,3).",
    )
    parser.add_argument(
        "--status",
        type=str,
        choices=["draft", "published"],
        default="published",
        help="Statut des articles crees (defaut published).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne rien modifier, afficher seulement les actions prevues.",
    )
    parser.add_argument(
        "--engage-existing",
        action="store_true",
        default=True,
        help="Ajouter likes/comments aussi sur les articles existants (defaut true).",
    )
    parser.add_argument(
        "--no-engage-existing",
        dest="engage_existing",
        action="store_false",
        help="Ajouter likes/comments seulement sur les articles nouvellement crees.",
    )
    args = parser.parse_args()

    if Path(".env").exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(".env"))
        except Exception:
            pass

    try:
        a_range = _parse_range(args.articles_per_user)
        l_range = _parse_range(args.likes_per_article)
        c_range = _parse_range(args.comments_per_article)
        r_range = _parse_range(args.replies_per_comment)
    except ValueError as e:
        print(f"[ERREUR] Range invalide : {e}")
        sys.exit(2)

    asyncio.run(
        seed_articles_only(
            articles_range_per_user=a_range,
            likes_range=l_range,
            comments_range=c_range,
            replies_range=r_range,
            dry_run=args.dry_run,
            status=args.status,
            engage_existing=args.engage_existing,
        )
    )


if __name__ == "__main__":
    main()
