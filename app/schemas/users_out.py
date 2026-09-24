from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.models.user import User as UserORM


class UserOut(BaseModel):
    """Utilisateur embarqué pour audit trail (validation, modération, rejet, paiement manuel).

    Garantit :
      - informations NON sensibles (pas de password_hash)
      - minimales si compte sans adhésion (superadmin) : id, email, roles, null prénom/nom/tel/commissariat
      - informations utiles à l'affichage : email + (prénom + nom) + commissariat + photo profil + rôles
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    email: str
    prenom: str | None = None
    nom: str | None = None
    tel_mobile: str | None = None
    commissariat: str | None = None
    roles: list[str] = Field(default_factory=list)
    profile_photo_url: str | None = None


async def to_user_out(user: "UserORM | None", roles: list[str] | None = None) -> UserOut | None:
    """Convertit un modèle ORM User (avec relations adhesion + roles chargés ou lazy) en UserOut.

    - Pas de User → None
    - `roles` : liste fournie (optimisation) ; sinon on parcourt user.roles (si loaded) ou []
    - Photo URL : préférence adhesion.profile_photo_url puis user.photo_url ou None
    - Prénom/Nom/Téléphone/Commissariat : préférence user directe (rempli pour admin via `ebdd4b6fc77d_add_nom_prenom_to_users`), sinon fallback adhesion
    """
    from app.core.urls import to_absolute_public_url

    if user is None:
        return None

    uid = getattr(user, "id", None)
    if uid is None:
        return None

    email_val = str(getattr(user, "email", "") or "").strip() or None
    if email_val is None:
        return None

    user_prenom = getattr(user, "prenom", None)
    user_nom = getattr(user, "nom", None)
    user_tel = None

    adhesion_rel = getattr(user, "adhesion", None) if hasattr(user, "adhesion") else None
    adhesion_commissariat: str | None = None
    photo_rel: str | None = None
    if adhesion_rel is not None:
        try:
            if not hasattr(adhesion_rel, "id"):
                adhesion_rel = None  # Non loaded (lazy) — on ignore
            else:
                user_prenom = user_prenom or getattr(adhesion_rel, "prenom", None)
                user_nom = user_nom or getattr(adhesion_rel, "nom", None)
                user_tel = getattr(adhesion_rel, "tel_mobile", None)
                adhesion_commissariat = getattr(adhesion_rel, "commissariat", None)
                photo_rel = getattr(adhesion_rel, "profile_photo_url", None) or getattr(
                    adhesion_rel, "photo_url", None
                )
        except Exception:
            adhesion_rel = None

    user_commissariat_attr = None
    try:
        user_commissariat_attr = getattr(user, "commissariat", None)
    except Exception:
        user_commissariat_attr = None

    commissariat_final = user_commissariat_attr or adhesion_commissariat or None

    if roles is None:
        loaded_roles = getattr(user, "roles", None) or []
        try:
            roles = []
            for r in loaded_roles:
                rval = getattr(r, "role", None)
                if rval is None:
                    continue
                if hasattr(rval, "value"):
                    roles.append(str(rval.value))
                else:
                    roles.append(str(rval))
        except Exception:
            roles = []

    photo_abs = to_absolute_public_url(photo_rel) if photo_rel else None

    return UserOut(
        id=uuid.UUID(str(uid)),
        email=email_val,
        prenom=str(user_prenom).strip() if user_prenom else None,
        nom=str(user_nom).strip() if user_nom else None,
        tel_mobile=str(user_tel).strip() if user_tel else None,
        commissariat=str(commissariat_final).strip() if commissariat_final else None,
        roles=list(roles or []),
        profile_photo_url=photo_abs,
    )


async def to_user_out_from_user_id(
    db: Any, user_id: str | uuid.UUID | None, *, roles: list[str] | None = None
) -> UserOut | None:
    """Récupère un User ORM (lazy safe) + convertit en UserOut."""
    if not user_id:
        return None
    from app.models.user import User as UserORM
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    uid = uuid.UUID(str(user_id))
    try:
        stmt = (
            select(UserORM)
            .where(UserORM.id == uid)
            .options(selectinload(UserORM.roles), selectinload(UserORM.adhesion))
        )
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
    except Exception:
        return None
    return await to_user_out(user, roles=roles)


async def _fetch_users_map(db: Any, user_ids: Iterable[uuid.UUID | str | None]) -> dict[uuid.UUID, UserOut]:
    """Charge 1 fois tous les users par batch, renvoie {user_id: UserOut}.

    Usage : `uids = {obj.a_user_id, obj.b_user_id, ...} ; m = await _fetch_users_map(db, uids) ; obj.a_user_out = m.get(obj.a_user_id)`
    Évite le N+1 classique sur les listings.
    """
    from app.models.user import User as UserORM
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    parsed: set[uuid.UUID] = set()
    for raw in user_ids:
        if not raw:
            continue
        try:
            parsed.add(uuid.UUID(str(raw)))
        except Exception:
            continue
    if not parsed:
        return {}
    try:
        stmt = (
            select(UserORM)
            .where(UserORM.id.in_(list(parsed)))
            .options(selectinload(UserORM.roles), selectinload(UserORM.adhesion))
        )
        res = await db.execute(stmt)
        users_list = list(res.scalars().all())
    except Exception:
        return {}
    out: dict[uuid.UUID, UserOut] = {}
    for u in users_list:
        mapped = await to_user_out(u)
        if mapped is not None:
            out[uuid.UUID(str(mapped.id))] = mapped
    return out


async def enrich_adhesion_acteurs_embedded(db: Any, items: Iterable[Any]) -> None:
    """Post-process pour injecter *_user embedded (UserOut) sur une liste d'objets Adhesion (ORM ou Pydantic).

    Colonnes exploitées :
      validation_accueil_user_id → valide_niveau1_par_user
      validation_directoire_user_id → valide_niveau2_par_user
      rejete_par_user_id → rejete_par_user
      en_complement_par_user_id → en_complement_par_user
      radie_par_user_id → radie_par_user

    Mutate les objets (setattr). Fonctionne sur ORM SA ou Pydantic (car Pydantic models acceptent setattr aussi).
    """
    ids: set[uuid.UUID] = set()
    items_list = list(items)
    attrs_map: list[tuple[str, str]] = [
        ("validation_accueil_user_id", "valide_niveau1_par_user"),
        ("validation_directoire_user_id", "valide_niveau2_par_user"),
        ("rejete_par_user_id", "rejete_par_user"),
        ("en_complement_par_user_id", "en_complement_par_user"),
        ("radie_par_user_id", "radie_par_user"),
    ]
    for a in items_list:
        for (src, _dst) in attrs_map:
            uid = getattr(a, src, None)
            if uid is not None:
                try:
                    ids.add(uuid.UUID(str(uid)))
                except Exception:
                    continue
    users = await _fetch_users_map(db, ids)
    for a in items_list:
        try:
            setattr(a, "valide_niveau1_at", getattr(a, "validation_accueil_at", None))
            setattr(a, "valide_niveau2_at", getattr(a, "validation_directoire_at", None))
        except Exception:
            pass
        for (src, dst) in attrs_map:
            uid = getattr(a, src, None)
            if uid is None:
                try:
                    setattr(a, dst, None)
                except Exception:
                    pass
                continue
            try:
                setattr(a, dst, users.get(uuid.UUID(str(uid))))
            except Exception:
                pass


async def enrich_articles_acteurs_embedded(db: Any, items: Iterable[Any]) -> None:
    """Même principe pour Article : author, validated_by, rejected_by, closed_by.

    → validés/rejet/clôturé = ArticleAuthorOut (nom/prénom/photo_id pour cohérence front).
    """
    from app.core.urls import to_absolute_public_url

    ids: set[uuid.UUID] = set()
    items_list = list(items)
    attrs_map: list[tuple[str, str]] = [
        ("author_id", "author"),
        ("validated_by_user_id", "validated_by_user"),
        ("rejected_by_user_id", "rejected_by_user"),
        ("closed_by_user_id", "closed_by_user"),
    ]
    for art in items_list:
        for (src, _dst) in attrs_map:
            uid = getattr(art, src, None)
            if uid is not None:
                try:
                    ids.add(uuid.UUID(str(uid)))
                except Exception:
                    continue
    users_raw = await _fetch_users_map(db, ids)
    # Convert UserOut → ArticleAuthorOut léger
    article_author_map: dict[uuid.UUID, Any] = {}
    try:
        from app.schemas.article import ArticleAuthorOut

        for u_uid, uo in users_raw.items():
            photo = getattr(uo, "profile_photo_url", None)
            article_author_map[u_uid] = ArticleAuthorOut(
                id=u_uid,
                nom=getattr(uo, "nom", None) or "",
                prenom=getattr(uo, "prenom", None) or "",
                profile_photo_url=photo,
            )
    except Exception:
        pass
    for art in items_list:
        for (src, dst) in attrs_map:
            uid = getattr(art, src, None)
            if uid is None:
                try:
                    setattr(art, dst, None)
                except Exception:
                    pass
                continue
            try:
                setattr(art, dst, article_author_map.get(uuid.UUID(str(uid))))
            except Exception:
                pass


async def enrich_cotisations_manuel_embedded(db: Any, items: Iterable[Any]) -> None:
    """Cotisation Mensuelle : paiement_manuel_par_user_id → paiement_manuel_par_user (UserOut)."""
    ids: set[uuid.UUID] = set()
    items_list = list(items)
    for cc in items_list:
        uid = getattr(cc, "paiement_manuel_par_user_id", None)
        if uid is not None:
            try:
                ids.add(uuid.UUID(str(uid)))
            except Exception:
                continue
    users = await _fetch_users_map(db, ids)
    for cc in items_list:
        uid = getattr(cc, "paiement_manuel_par_user_id", None)
        try:
            if uid is None:
                setattr(cc, "paiement_manuel_par_user", None)
            else:
                setattr(cc, "paiement_manuel_par_user", users.get(uuid.UUID(str(uid))))
        except Exception:
            pass
