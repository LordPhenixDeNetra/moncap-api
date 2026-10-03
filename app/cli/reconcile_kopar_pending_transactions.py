"""
Rapprochement (reconciliation) Kopar / BDD MONCAP - fallback anti-régression webhook KO.

But : si le webhook Kopar n'a pas été reçu (ou rejeté en 403 signature), la transaction
reste éternellement en statut "new" même si l'utilisateur a réellement payé sur Wave/OM.
Ce job :
  1. Récupère toutes les lignes transactions_kopar.statut IN (new, pending) créées il y a
     au moins N minutes (RECONCILE_KOPAR_OLDER_MINUTES).
  2. Interroge Kopar `GET /api/v2/transaction/{kopar_token}` pour connaître le vrai statut.
  3. Applique le statut via PaiementOrchestratorService.appliquer_statut_kopar : EXACTEMENT
     le même code que le webhook (aucune logique dupliquée ici) :
       - success + adhesion    → adhesions.paiement_confirme = TRUE + email
       - success + cotisation  → les N mois de la période (1/3/6/12) passent à payee + email
       - failed / cancelled / refunded → statut final enregistré (plus retraité ensuite)
     Verrou ligne + idempotence : sans risque si le webhook arrive en même temps.
  4. Une transaction par ligne : une erreur n'empêche pas les autres d'être rattrapées.
     Code retour 1 si au moins une erreur (visible par le CRON / la supervision).

Mode d'emploi :
    # Mode dry-run par défaut (NE TOUCHE PAS À LA BASE) :
    python -m app.cli.reconcile_kopar_pending_transactions

    # Appliquer les changements en BDD :
    python -m app.cli.reconcile_kopar_pending_transactions --apply

    # Un seul tour (one-shot, idéal pour CRON every 5 min Alwaysdata) :
    python -m app.cli.reconcile_kopar_pending_transactions --apply --once

    # Mode démon infini (boucle toutes les RECONCILE_KOPAR_POLL_SECONDS) :
    python -m app.cli.reconcile_kopar_pending_transactions --apply --daemon

    # Désactivé via .env RECONCILE_KOPAR_ENABLED=false → script exit 0 immédiat.
    # Surcharger avec --force pour lancer malgré tout (mode debug prod).

Configuration dans .env / settings :
    RECONCILE_KOPAR_ENABLED=true          (default true)
    RECONCILE_KOPAR_OLDER_MINUTES=5       (default 5 min, donne une chance au webhook)
    RECONCILE_KOPAR_POLL_SECONDS=300      (default 300s = 5min, boucle daemon)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Tuple

from fastapi import BackgroundTasks
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_sessionmaker
from app.models.paiements import StatutTransactionKopar, TransactionKopar
from app.services.kopar import KoparClient, KoparError
from app.services.paiement_orchestrator import PaiementOrchestratorService


def _print(level: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    # Safe Windows cp1252 : remplacer les fleches / symboles non encodables par equivalents ascii.
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
    # UTF-8 par sécurité sur Windows STDOUT cp1252 : sys.stdout reconfigure en utf-8 si possible.
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
        # Dernier recours : tout remplacer par '?'.
        alt = safe_msg.encode("cp1252", errors="replace").decode("cp1252")
        print(f"[{ts}] [{level}] {alt}", flush=True)


async def _get_pending_transactions(
    db: AsyncSession, older_than_minutes: int
) -> list[TransactionKopar]:
    om = int(older_than_minutes or 0)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=om)
    stmt = (
        select(TransactionKopar)
        .where(
            and_(
                TransactionKopar.kopar_token.is_not(None),
                TransactionKopar.statut.in_(
                    [StatutTransactionKopar.new, StatutTransactionKopar.pending]
                ),
                TransactionKopar.created_at <= cutoff,
            )
        )
        .order_by(TransactionKopar.created_at.asc())
    )
    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    return rows


async def _reconcile_one_tour(
    *, dry_run: bool, older_minutes_override: int | None = None
) -> Tuple[int, int, int, int]:
    """Un seul passage. Retourne (candidats, marques_success, autres_marques, erreurs).

    Chaque transaction est traitée dans SA PROPRE session/transaction SQL : une erreur sur
    l'une est loggée, comptée, et n'empêche pas les autres d'être rattrapées.
    Le métier est délégué à PaiementOrchestratorService.appliquer_statut_kopar, le même code
    que le webhook (verrou ligne, idempotence, statuts finaux protégés, emails).
    """
    settings = get_settings()
    older_minutes = (
        int(older_minutes_override)
        if older_minutes_override is not None
        else max(1, int(settings.reconcile_kopar_older_minutes or 5))
    )
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        candidats = [
            (tx.id, str(tx.kopar_token or "").strip(), tx.statut)
            for tx in await _get_pending_transactions(db, older_minutes)
        ]
    _print(
        "INFO",
        f"Tour démarré : {len(candidats)} transaction(s) en statut new/pending "
        f"aged >= {older_minutes} min.",
    )
    if not candidats:
        return 0, 0, 0, 0

    client = KoparClient()
    marques_success = autres_marques = erreurs = 0

    for tx_id, token, statut_bd in candidats:
        if not token:
            _print("WARN", f"tx {tx_id} : kopar_token vide (skip).")
            continue
        try:
            detail = await client.get_transaction_detail(token)
        except KoparError as e:
            erreurs += 1
            _print(
                "ERROR",
                f"tx {tx_id} : appel Kopar en échec HTTP={e.status_code} "
                f"kopar_error_code={e.kopar_error_code} : {e}",
            )
            continue
        except Exception as exc:
            erreurs += 1
            _print("ERROR", f"tx {tx_id} : exception get_transaction_detail : {exc!r}")
            continue

        nouveau = detail.statut
        if nouveau in (StatutTransactionKopar.new, StatutTransactionKopar.pending):
            continue  # toujours en cours côté Kopar : on retentera au prochain passage

        label = f"tx {tx_id} (token...{token[-6:]}) Kopar={nouveau.value} vs BDD={statut_bd.value}"
        if dry_run:
            _print("DRY", f"{label} -> serait appliqué")
            if nouveau == StatutTransactionKopar.success:
                marques_success += 1
            else:
                autres_marques += 1
            continue

        background_tasks = BackgroundTasks()
        try:
            async with sessionmaker() as db:
                action = await PaiementOrchestratorService(db).appliquer_statut_kopar(
                    tx_id,
                    nouveau,
                    body={"source": "reconcile_job", "kopar_detail": detail.data},
                    background_tasks=background_tasks,
                )
                await db.commit()
        except Exception as exc:
            erreurs += 1
            _print("ERROR", f"{label} -> ÉCHEC, rien n'est appliqué (retenté au prochain passage) : {exc!r}")
            continue

        if nouveau == StatutTransactionKopar.success:
            marques_success += 1
        else:
            autres_marques += 1
        _print("OK", f"{label} -> {action}")

        # Emails de confirmation APRÈS commit, comme pour le webhook
        try:
            await background_tasks()
        except Exception as exc:
            _print("WARN", f"tx {tx_id} : email de confirmation non envoyé : {exc!r}")

    return len(candidats), marques_success, autres_marques, erreurs


async def run_async(
    *,
    once: bool,
    daemon: bool,
    dry_run: bool,
    force: bool,
    older_minutes: int | None = None,
) -> int:
    settings = get_settings()

    if not settings.reconcile_kopar_enabled and not force:
        _print("INFO", "RECONCILE_KOPAR_ENABLED=false dans .env. Sortie anticipée (sans erreur).")
        return 0
    if not settings.kopar_enabled:
        _print("WARN", "KOPAR_ENABLED=false dans .env. Aucun rapprochement possible.")
        return 0
    if force:
        _print("INFO", "--force : ignore RECONCILE_KOPAR_ENABLED.")

    if daemon and once:
        _print("WARN", "Les deux drapeaux --daemon et --once sont incompatibles. Mode --once privilégié.")
        daemon = False

    if dry_run:
        _print("INFO", "Mode DRY-RUN. Lecture seule, Aucun commit en base. Utilisez --apply pour appliquer.")
    else:
        _print("INFO", "Mode APPLY. Les changements seront commités en base de données.")

    period = max(5, int(settings.reconcile_kopar_poll_seconds or 300))

    if daemon:
        _print("INFO", f"Mode DAEMON. Boucle infinie toutes les {period}s. Ctrl+C pour arrêter.")
        while True:
            debut = time.monotonic()
            try:
                await _reconcile_one_tour(dry_run=dry_run, older_minutes_override=older_minutes)
            except KeyboardInterrupt:
                _print("INFO", "Interruption clavier. Sortie.")
                return 0
            except Exception as exc:
                _print("ERROR", f"Exception tour daemon : {exc!r}")
            elapsed = time.monotonic() - debut
            sleep_for = max(0.0, period - elapsed)
            await asyncio.sleep(sleep_for)

    # one-shot
    debut = time.monotonic()
    total_cands, ok, autres, erreurs = await _reconcile_one_tour(
        dry_run=dry_run, older_minutes_override=older_minutes
    )
    duree_ms = int((time.monotonic() - debut) * 1000)
    _print(
        "INFO" if not erreurs else "ERROR",
        f"Tour one-shot terminé en {duree_ms}ms. "
        f"Candidats={total_cands} ; marqués SUCCESS={ok} ; autres statuts={autres} ; ERREURS={erreurs}.",
    )
    # Code retour 1 si erreurs : le CRON / la supervision le voit (au lieu d'un faux succès)
    return 1 if erreurs else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rapprochement Kopar / BDD MONCAP - fallback anti-régression webhook KO."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Appliquer les changements en base. Sinon mode dry-run (défaut).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mode lecture seule (DRY-RUN, défaut). Explicitement l'inverse de --apply.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Un seul passage (one-shot), typiquement pour un CRON.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Mode démon infini. Période = RECONCILE_KOPAR_POLL_SECONDS du .env.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignorer RECONCILE_KOPAR_ENABLED=false dans .env (mode debug).",
    )
    parser.add_argument(
        "--older-minutes",
        type=int,
        default=None,
        help="Override RECONCILE_KOPAR_OLDER_MINUTES (ex: 0 = inclure memes les tx tres recentes).",
    )
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        print(
            "[WARN] Vous avez passé --apply et --dry-run. Dry-run prioritaire (aucun changement appliqué).",
            file=sys.stderr,
        )
    dry_run = bool(args.dry_run) or not bool(args.apply)
    try:
        return asyncio.run(
            run_async(
                once=bool(args.once),
                daemon=bool(args.daemon),
                dry_run=dry_run,
                force=bool(args.force),
                older_minutes=args.older_minutes,
            )
        )
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
