"""
Radiation automatique : membres avec 3+ mois impayés CONSÉCUTIFS.

Règle métier (cf settings.radiation_delai_mois_impayes_consecutifs, défaut 3) :
  - NE TRAITE QUE les adhésions statut="validee" (pas en_attente / rejetee / complement / deja radiee)
  - EXCLUT les rôles privilégiés (Admin, Comité d'accueil, CD, CC, CR, Modérateur)
  - EXCLUT les nouvelles recrues : nb_cotisations_generees <= delai_mois
    (autrement dit il faut AU MOINS delai_mois + 1 cotisations en base, sinon protection "nouveau")
  - Le "streak" compte les impayés EN PARTANT du mois présent vers le passé,
    jusqu'à rencontrer un statut payee / annulee OU un mois absent de la BDD.
    Un ancien streak de 3 mois (il y a 1 an) suivi de paiements réguliers
    NE DÉCLENCHE PAS la radiation.

Règle "RADIE ATOMIQUE" :
  - adhesions.statut → radiee
  - adhesions.radie_at + radiation_reason_code + radiation_motif + radie_par_user_id (NULL car auto)
  - users.is_active → false + disabled_at + disabled_reason_code + disabled_motif + disabled_by_user_id NULL
  - Email de notification ENVOYÉ SI MAIL_ENABLED=true (best-effort, jamais bloquant)

Réactivation : 100% MANUELLE ADMIN (aucun réactivation auto à la réception d'un paiement).

Mode d'emploi :
    # DRY-RUN par défaut : liste les candidats, NE TOUCHE PAS À LA BASE.
    poetry run python -m app.cli.apply_radiations

    # Appliquer les radiations en BDD (confirmation implicite) :
    poetry run python -m app.cli.apply_radiations --apply

    # Limiter à N radiations pour tester en douceur :
    poetry run python -m app.cli.apply_radiations --apply --limit 10

    # Override settings.radiation_automatique_enabled=false :
    poetry run python -m app.cli.apply_radiations --apply --force

    # Calcul sur un autre mois que le courant (ex: retard CRON, rattrapage) :
    poetry run python -m app.cli.apply_radiations --apply --annee 2026 --mois 5
    # ou via --as-of ISO :
    poetry run python -m app.cli.apply_radiations --apply --as-of 2026-05-15T00:00:00Z
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from typing import Iterable

from app.core.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.models.enums import DisabledReason
from app.repositories.adhesions import AdhesionRepository
from app.services.mail import send_email_best_effort
from app.services.radiation_mail_templates import (
    build_radiation_notification,
    resolve_recipient_email,
)
from app.services.radiation_service import RadiationService


# ===================================================================
#  Helpers affichage sécurisé (UTF-8 + ASCII safe Windows cp1252)
# ===================================================================

def _print(level: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_msg = (
        (msg or "")
        .replace("→", "->")
        .replace("←", "<-")
        .replace("⟷", "<->")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("≠", "!=")
        .replace("«", "<<")
        .replace("»", ">>")
        .replace("€", "EUR")
        .replace("£", "GBP")
    )
    stdout = sys.stdout
    try:
        buf = getattr(stdout, "buffer", None)
        line = f"[{ts}] [{level}] {safe_msg}" + "\n"
        if buf is not None:
            buf.write(line.encode("utf-8", errors="replace"))
            buf.flush()
            return
    except Exception:
        pass
    try:
        print(f"[{ts}] [{level}] {safe_msg}", flush=True)
    except Exception:
        try:
            alt = safe_msg.encode("cp1252", errors="replace").decode("cp1252")
            print(f"[{ts}] [{level}] {alt}", flush=True)
        except Exception:
            pass


def _label_mois(annee: int, mois: int) -> str:
    noms = [
        "Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre",
    ]
    return f"{noms[mois-1] if 1 <= mois <= 12 else f'M{mois}'} {annee}"


def _format_mois_concernes(items: Iterable) -> str:
    parts = []
    for m in items:
        if isinstance(m, tuple) and len(m) == 2:
            a, mo = int(m[0]), int(m[1])
        else:
            a = int(getattr(m, "annee", 0))
            mo = int(getattr(m, "mois", 0))
        if a and mo:
            parts.append(_label_mois(a, mo))
    if not parts:
        return "-"
    return ", ".join(parts)


# ===================================================================
#  CLI main
# ===================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Radiation automatique des membres avec N mois impayés consécutifs (DRY-RUN PAR DEFAUT).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Appliquer effectivement les radiations en base. SANS CET OPTION = dry-run (aucune modification).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignorer RADIATION_AUTOMATIQUE_ENABLED=false dans les settings (override prod).",
    )
    parser.add_argument(
        "--annee",
        type=int,
        default=None,
        help="Année cible pour le calcul du streak (defaut: année en cours). Ignoré si --as-of fourni.",
    )
    parser.add_argument(
        "--mois",
        type=int,
        default=None,
        help="Mois cible 1-12 pour le calcul (defaut: mois en cours). Ignoré si --as-of fourni.",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Date/heure ISO de référence pour le calcul du streak. Ex: 2026-05-15T00:00:00Z",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limiter le nombre de radiations appliquées (idéal pour tests prod progressifs).",
    )
    parser.add_argument(
        "--delai-mois",
        type=int,
        default=None,
        help="Override temporaire le seuil de mois impayés consécutifs (settings défaut 3).",
    )
    return parser


def _parse_as_of(args: argparse.Namespace) -> datetime:
    if args.as_of:
        s = args.as_of.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            _print("ERREUR", f"--as-of invalide (attendu ISO 8601) : {e}")
            sys.exit(2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    a = args.annee if args.annee is not None else date.today().year
    m = args.mois if args.mois is not None else date.today().month
    if not (1 <= m <= 12):
        _print("ERREUR", f"mois invalide {m} (doit etre 1-12)")
        sys.exit(2)
    return datetime(a, m, 1, 0, 0, 0, tzinfo=timezone.utc)


async def _run() -> int:
    settings = get_settings()
    parser = _build_parser()
    args = parser.parse_args()

    if not settings.radiation_automatique_enabled and not args.force:
        _print(
            "INFO",
            "Radiation automatique désactivée via settings.RADIATION_AUTOMATIQUE_ENABLED=false. "
            "Utilisez --force pour forcer l'exécution malgré tout, ou réactivez la feature dans le .env.",
        )
        return 0

    delai_mois = (
        args.delai_mois
        if args.delai_mois is not None
        else settings.radiation_delai_mois_impayes_consecutifs
    )
    if delai_mois < 1:
        delai_mois = 1

    as_of = _parse_as_of(args)

    dry_run = not args.apply
    limit = max(0, int(args.limit)) if args.limit is not None else None

    _print(
        "INFO",
        (
            f"Parametres : dry_run={dry_run} force={args.force} "
            f"delai_mois={delai_mois} as_of={as_of.isoformat()} limit={limit if limit is not None else 'ILLIMITE'}"
        ),
    )

    if dry_run:
        _print("INFO", "Mode DRY-RUN : aucune modification en base. Pour appliquer, relancez avec --apply.")

    # ------------------------------------------------------------------
    #  Phase 1 : détecter les candidats via RadiationService
    # ------------------------------------------------------------------

    async with AsyncSessionLocal() as session:
        service = RadiationService(session)
        candidats = await service.list_candidates(
            as_of=as_of,
            exclude_privileged_roles=True,
            delai_mois=delai_mois,
            limit=limit,
        )
        if not candidats:
            _print("OK", f"Aucun candidat detecté avec seuil={delai_mois} mois impayés consécutifs. Rien à faire.")
            return 0

        _print(
            "INFO",
            f"{len(candidats)} candidat(s) détecté(s) avec ≥ {delai_mois} mois impayés consécutifs :",
        )
        for idx, c in enumerate(candidats, 1):
            lignes = [
                f"  [#{idx}] adhesion={c.adhesion_id} {c.adhesion_prenom} {c.adhesion_nom}",
                f"         email={c.email} tel={c.tel_mobile}",
                f"         streak={c.streak_mois_impayes} mois | mois concernes : {_format_mois_concernes(c.mois_concernes)}",
            ]
            for ligne in lignes:
                _print("CANDIDAT", ligne)

        if dry_run:
            _print(
                "INFO",
                f"DRY-RUN : {len(candidats)} radiation(s) NON appliquée(s). "
                f"Relancez avec --apply pour persister en base.",
            )
            return 0

        # ------------------------------------------------------------------
        #  Phase 2 : APPLY (commit par adhesion pour ne pas casser le lot)
        # ------------------------------------------------------------------

        total_radies = 0
        total_erreurs = 0

        for idx, c in enumerate(candidats, 1):
            try:
                motif_auto = (
                    f"Radiation automatique via CRON/CLI — {c.streak_mois_impayes} mois impayés consécutifs "
                    f"(as_of {as_of.date().isoformat()}). Mois concernes : "
                    f"{_format_mois_concernes(c.mois_concernes)}."
                )
                adhesion, user_after = await service.apply_radiation(
                    adhesion_id=c.adhesion_id,
                    reason_code=DisabledReason.AUTOMATIQUE_3_MOIS,
                    motif=motif_auto,
                    radie_par_user_id=None,
                )
                await session.commit()

                # Email best-effort (jamais bloquant)
                try:
                    if settings.mail_enabled:
                        adhesion_fresh = await AdhesionRepository(session).get_by_id(adhesion.id)
                        user_fresh = (
                            adhesion_fresh.user_account
                            if adhesion_fresh is not None and getattr(adhesion_fresh, "user_account", None)
                            else None
                        )
                        email_to = None
                        if adhesion_fresh is not None:
                            email_to = resolve_recipient_email(
                                adhesion=adhesion_fresh, user=user_fresh
                            )
                        if email_to:
                            mois_tuples = [
                                (m.annee, m.mois) for m in c.mois_concernes
                            ]
                            subj, text, html = build_radiation_notification(
                                adhesion=adhesion_fresh or adhesion,
                                user=user_fresh or user_after,
                                motif=motif_auto,
                                reason_code=DisabledReason.AUTOMATIQUE_3_MOIS,
                                mois_concernes=mois_tuples,
                                base_url=settings.public_base_url,
                            )
                            send_email_best_effort(
                                to=email_to,
                                subject=subj,
                                text=text,
                                html=html,
                                settings=settings,
                            )
                except Exception:  # noqa: BLE001
                    _print(
                        "WARN",
                        f"  [#{idx}] Email notification échoué (best-effort, ignoré) : adhesion={c.adhesion_id}",
                    )

                total_radies += 1
                _print(
                    "OK",
                    f"  [#{idx}] Radiation OK → {c.adhesion_prenom} {c.adhesion_nom} (adhesion={c.adhesion_id})",
                )
            except Exception as e:  # noqa: BLE001
                total_erreurs += 1
                _print(
                    "ERREUR",
                    (
                        f"  [#{idx}] Echec radiation adhesion={c.adhesion_id} "
                        f"{c.adhesion_prenom} {c.adhesion_nom} : {e!r}"
                    ),
                )
                # Rollback partiel pour cette adhesion seulement
                try:
                    await session.rollback()
                except Exception:
                    pass

    _print(
        "INFO",
        f"Terminé. Radiations appliquées = {total_radies}, Erreurs = {total_erreurs}",
    )
    return 0 if total_erreurs == 0 else 1


def main() -> None:
    try:
        rc = asyncio.run(_run())
    except KeyboardInterrupt:
        _print("WARN", "Interruption utilisateur.")
        rc = 130
    except Exception as exc:  # noqa: BLE001
        _print("ERREUR", f"Exception non gérée dans le CLI : {exc!r}")
        rc = 2
    sys.exit(rc)


if __name__ == "__main__":
    main()
