"""Script CLI de récupération d'urgence : REBUILDE la table `adhesions` à partir de `users`.

Cas d'usage : Admin a supprimé par erreur TOUTES les lignes de `adhesions`.
Les comptes `users` existent toujours → on recrée 1 adhesion PAR user, avec
des valeurs par défaut sensées pour les champs requis non présents dans users.

Caractéristiques :
- **100% idempotent** : ne touche JAMAIS aux users ayant déjà `adhesion_id IS NOT NULL`.
- **Dry-run par défaut** : `--dry-run` affiche ce qui serait fait sans rien toucher.
- **Pour appliquer** : `--apply`.
- Génère aussi un fichier SQL de sortie `rebuild_adhesions_from_users.sql` pour audit manuel.

Usage :
    # 1) Voir ce que le script va faire (SANS MODIFIER LA BDD) :
    python -m app.cli.rebuild_adhesions_from_users

    # 2) Appliquer réellement :
    python -m app.cli.rebuild_adhesions_from_users --apply

    # 3) Avec status souhaité différent (par exemple tout valider pour tests) :
    python -m app.cli.rebuild_adhesions_from_users --apply --status validee
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus, PaymentMode, EngagementType
from app.models.user import User
from app.core.settings import get_settings

settings = get_settings()


@dataclass
class RebuildStats:
    users_total: int = 0
    users_avec_adhesion: int = 0
    users_sans_adhesion: int = 0
    adhesions_inserees: int = 0
    users_skipped: int = 0


def _placeholder_date_naissance(user_email: str) -> date:
    """Placeholder non ambigue pour un user dont on n'a pas date_naissance.

    Date par défaut = 01/01/1980 (majorité, peu probable de poser problème).
    On fera 2000-01-01 pour les emails contenant '@gmail.com / @hotmail / etc.'
    → pas de sens métier, juste remplir NOT NULL.
    """
    h = hash(user_email or "")
    year = 1980 + (abs(h) % 25)  # 1980..2004
    month = 1 + (abs(h >> 4) % 12)
    day = 1 + (abs(h >> 8) % 28)
    return date(year, month, day)


def _placeholder_cni(user_email: str) -> str:
    """CNI unique placeholder (colonne NOT NULL)."""
    base = (user_email or "user").replace("@", "AT").replace(".", "DOT")
    suffix = str(abs(hash(user_email or "")))[-8:]
    return f"CNI-REC{base.upper()[:20]}-{suffix}"


def _placeholder_profession(prenom: str, nom: str) -> str:
    return "À compléter"


def _placeholder_fonction_pro() -> str:
    return "À compléter"


def _placeholder_commissariat(email: str, commissariat_from_email: str | None = None) -> str:
    if commissariat_from_email:
        return commissariat_from_email
    if "comite_accueil" in email:
        return "Comité Accueil"
    if "comite_directoire" in email:
        return "Comité Directoire"
    if "@moncap.com" in email or "@cices.sn" in email:
        return "Administration MONCAP"
    if "@innovamind.tech" in email or "neta" in email.lower() or "dev" in email.lower():
        return "Équipe Technique / Développement"
    if "admin" in email.lower():
        return "Administration"
    return "Commissariat à définir"


def _placeholder_tel_mobile(email: str, nom: str, prenom: str) -> str:
    h = abs(hash(f"{email}|{nom}|{prenom}"))
    suffix = str(h)[-7:]  # 7 chiffres
    return f"+22177{suffix}"


def build_adhesion_for_user(
    user: User,
    *,
    default_status: AdhesionStatus,
    paiement_confirme_force: bool | None = None,
) -> Adhesion:
    """Construit un objet Adhesion VALIDE pour un user, avec placeholders pour
    les champs NOT NULL absents de la table users.

    Seuls nom/prenom/email viennent de users.
    """
    now = datetime.utcnow()
    statut = default_status
    # Forcer certains users en validee (admin, comité connu, etc.)
    email_low = (user.email or "").lower()
    if (
        email_low.endswith("@moncap.com")
        or "comite_" in email_low
        or email_low == "admin@example.com"
    ):
        statut = AdhesionStatus.validee
        paiement_confirme_force = True
    # Users techniques / devs : valider pour tests
    if "@innovamind.tech" in email_low or email_low in {
        "netradevlpdn@gmail.com",
        "ded08acf-facf-4ed4-b198-707fbd7ba7f3",
    }:
        statut = AdhesionStatus.validee
    adhesion = Adhesion(
        id=uuid.uuid4(),
        nom=user.nom or "Nom inconnu",
        prenom=user.prenom or "Prénom inconnu",
        date_naissance=_placeholder_date_naissance(user.email or f"u-{user.id}"),
        lieu_naissance="Dakar (à compléter)",
        profession=_placeholder_profession(user.prenom or "", user.nom or ""),
        tel_mobile=_placeholder_tel_mobile(user.email or "", user.nom or "", user.prenom or ""),
        tel_fixe=None,
        email=user.email or "",
        cni=_placeholder_cni(user.email or f"u-{user.id}"),
        carte_electeur=None,
        carte_pastef=None,
        niveau_etude=None,
        annees_experience=None,
        biographie=None,
        est_diaspora=False,
        fonction_professionnelle=_placeholder_fonction_pro(),
        engagement=[],
        commissariat=_placeholder_commissariat(user.email or ""),
        commissariat_scientifique_principal=None,
        commissariat_scientifique_secondaire=None,
        mode_paiement=PaymentMode.kopar_pay,
        montant_adhesion=getattr(settings, "default_adhesion_fcfa", 5) or 5,
        paiement_confirme=paiement_confirme_force
        if paiement_confirme_force is not None
        else (statut == AdhesionStatus.validee),
        reference_paiement=None,
        statut=statut,
        motif_rejet=None,
        created_at=user.created_at or now,
        updated_at=now,
        deleted_at=None,
    )
    return adhesion


async def run(dry_run: bool = True, default_status_str: str = "en_attente") -> RebuildStats:
    stats = RebuildStats()
    try:
        default_status = AdhesionStatus(default_status_str)
    except Exception:
        default_status = AdhesionStatus.en_attente
    sql_lines: list[str] = []
    async with AsyncSessionLocal() as db:
        q_users = select(User).order_by(User.created_at.asc())
        res = await db.execute(q_users)
        users: list[User] = list(res.scalars().unique().all())
        stats.users_total = len(users)
        print("\n" + "=" * 100)
        print(f"Total users en base : {stats.users_total}")
        print("=" * 100)
        for u in users:
            if u.adhesion_id is not None:
                stats.users_avec_adhesion += 1
                print(f"  ✅ SKIP user  {u.email:40s}  (adhesion_id={u.adhesion_id} déja lié)")
                continue
            stats.users_sans_adhesion += 1
            adhesion = build_adhesion_for_user(u, default_status=default_status)
            print(
                f"  🆕 {'DRY ' if dry_run else ''}CREER  {u.email:40s}"
                f"  adhesion_id={adhesion.id}"
                f"  statut={adhesion.statut.value:16s}"
                f"  paiement_confirme={adhesion.paiement_confirme}"
                f"  montant_adhesion={adhesion.montant_adhesion}"
            )
            # Audit SQL (for debug)
            sql_lines.append(
                f"-- User: {u.email} (user_id={u.id}) -> new adhesion_id={adhesion.id}"
            )
            sql_lines.append(
                "INSERT INTO public.adhesions (id,nom,prenom,date_naissance,lieu_naissance,"
                "profession,tel_mobile,email,cni,fonction_professionnelle,engagement,"
                "commissariat,mode_paiement,montant_adhesion,paiement_confirme,statut,"
                "created_at,updated_at,est_diaspora) VALUES ("
                f"'{adhesion.id}','"
                + str(adhesion.nom).replace("'", "''")
                + "','"
                + str(adhesion.prenom).replace("'", "''")
                + f"','{adhesion.date_naissance.isoformat()}','"
                + str(adhesion.lieu_naissance).replace("'", "''")
                + "','"
                + str(adhesion.profession).replace("'", "''")
                + "','"
                + str(adhesion.tel_mobile).replace("'", "''")
                + "','"
                + (adhesion.email or "").replace("'", "''")
                + "','"
                + (adhesion.cni or "").replace("'", "''")
                + "','"
                + str(adhesion.fonction_professionnelle).replace("'", "''")
                + f"','[]','"
                + str(adhesion.commissariat).replace("'", "''")
                + f"','{adhesion.mode_paiement.value}',{adhesion.montant_adhesion},"
                + f"{'TRUE' if adhesion.paiement_confirme else 'FALSE'},"
                + f"'{adhesion.statut.value}',"
                + f"'{adhesion.created_at.isoformat() if adhesion.created_at else 'NOW()'}',"
                + f"'NOW()',FALSE);"
            )
            sql_lines.append(
                f"UPDATE public.users SET adhesion_id='{adhesion.id}' WHERE id='{u.id}';\n"
            )
            if not dry_run:
                db.add(adhesion)
                await db.flush()
                u.adhesion_id = adhesion.id
                stats.adhesions_inserees += 1
        if not dry_run:
            await db.commit()
    # Write SQL audit file (always)
    try:
        sql_path = settings.storage_dir.parent / "rebuild_adhesions_from_users.sql"
        sql_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write(
                f"-- Script généré {datetime.now().isoformat()}"
                + f"  (DRY_RUN={'Y' if dry_run else 'N'}"
                + f"  TOTAL_USERS={stats.users_total}"
                + f"  USERS_SANS_ADH={stats.users_sans_adhesion}"
                + f"  INSERES={stats.adhesions_inserees})\n"
            )
            f.write("BEGIN;\n")
            for line in sql_lines:
                f.write(line + "\n")
            f.write("COMMIT;\n")
        print(f"\n📄 SQL de debug écrit dans : {sql_path}")
    except Exception as e:
        print(f"\n⚠️  Impossible écrire fichier SQL : {e}")
    print("\n" + "=" * 100)
    print("RÉSUMÉ")
    print("=" * 100)
    print(f"  Users total                        : {stats.users_total}")
    print(f"  Users ayant déja adhesion_id      : {stats.users_avec_adhesion}")
    print(f"  Users SANS adhesion_id (à créer)  : {stats.users_sans_adhesion}")
    if dry_run:
        print(f"  Adhésions QUI SERONT créées        : {stats.users_sans_adhesion}  (DRY-RUN, rien appliqué)")
        print(f"  🚨 POUR APPLIQUER : relance avec  --apply")
    else:
        print(f"  ✅ Adhésions CRÉÉES & COMMITÉES    : {stats.adhesions_inserees}")
        print(f"  Users liés users.adhesion_id → OK : {stats.adhesions_inserees}")
    print("=" * 100)
    return stats


def main():
    p = argparse.ArgumentParser(description="Reconstruire adhesions depuis users.")
    p.add_argument("--apply", action="store_true", help="Appliquer réellement (défaut = dry-run)")
    p.add_argument(
        "--status",
        default="en_attente",
        choices=[e.value for e in AdhesionStatus],
        help="Statut par défaut pour les adhésions créées (défaut = en_attente).",
    )
    args = p.parse_args()
    import asyncio

    stats = asyncio.run(run(dry_run=not args.apply, default_status_str=args.status))
    if args.apply and stats.adhesions_inserees == 0 and stats.users_sans_adhesion == 0:
        print("\n✅ Rien à faire : tous les users ont déjà leur adhesion_id.")
        sys.exit(0)
    if not args.apply:
        print(
            "\n⚠️  DRY RUN TERMINÉ. Rien n'a été modifié en base."
            "\n👉 Vérifiez la liste ci-dessus puis relancez avec :  --apply\n"
        )
    else:
        print("\n✅ TRAITEMENT APPLIQUÉ.")
        print("👉 Vérifiez le fichier rebuild_adhesions_from_users.sql pour audit manuel.")
        print("👉 Si besoin de modifier les placeholders, éditez les via l'admin MONCAP (champs: date_naissance, lieu_naissance, profession, tel_mobile, cni, commissariat, fonction_professionnelle, niveau_etude, etc.)")


if __name__ == "__main__":
    main()
