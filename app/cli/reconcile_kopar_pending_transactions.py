"""
Rapprochement (reconciliation) Kopar / BDD MONCAP - fallback anti-régression webhook KO.

But : si le webhook Kopar n'a pas été reçu (ou rejeté en 403 signature), la transaction
reste éternellement en statut "new" même si l'utilisateur a réellement payé sur Wave/OM.
Ce job :
  1. Récupère toutes les lignes transactions_kopar.statut IN (new, pending) créées il y a
     au moins N minutes (RECONCILE_KOPAR_OLDER_MINUTES).
  2. Interroge Kopar `GET /api/v2/transaction/{kopar_token}` pour connaître le vrai statut.
  3. Si Kopar dit "success" → on EXÉCUTE exactement le même workflow que le webhook SUCCESS :
       - set transactions_kopar.statut = success
       - si type_transaction = adhesion → set adhesions.paiement_confirme = TRUE
       - si type_transaction = cotisation → set cotisations_mensuelles.statut = payee
  4. Si Kopar dit "failed / cancelled / refunded" → on marque transactions_kopar.statut
     à la bonne valeur (pour ne plus le traiter à chaque boucle).

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
from typing import Any, Tuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.models.adhesion import Adhesion
from app.models.paiements import (
    CotisationMensuelle,
    CotisationStatut,
    StatutTransactionKopar,
    TransactionKopar,
    TypeTransactionKopar,
)
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


async def _get_adhesion(db: AsyncSession, aid: Any) -> Adhesion | None:
    if aid is None:
        return None
    return await db.get(Adhesion, aid)


async def _get_cotisation(db: AsyncSession, cid: Any) -> CotisationMensuelle | None:
    if cid is None:
        return None
    return await db.get(CotisationMensuelle, cid)


async def _apply_success_on_business_records(
    db: AsyncSession,
    tx: TransactionKopar,
    *,
    dry_run: bool,
) -> list[str]:
    """Applique exactement le même workflow que processer_webhook SUCCESS.
    Retourne une liste d'actions décrites pour les logs."""
    actions: list[str] = []
    orchestrator = PaiementOrchestratorService(db)

    try:
        if tx.type_transaction == TypeTransactionKopar.adhesion and tx.adhesion_id:
            adh = await _get_adhesion(db, tx.adhesion_id)
            if adh is None:
                actions.append("adhesion introuvable (skip)")
            else:
                adh.paiement_confirme = True
                if (
                    adh.reference_paiement is None
                    or len(str(adh.reference_paiement or "").strip()) == 0
                ):
                    adh.reference_paiement = (
                        f"KOPAR-RECONCILE-{str(tx.id)[:8].upper()}"
                    )
                actions.append(f"adhesion {tx.adhesion_id} -> paiement_confirme=true")
                await orchestrator.transactions.update_after_webhook(
                    tx.id,
                    StatutTransactionKopar.success,
                    webhook_body={"reconcile_job": True, "method": "kopar_get_transaction_poll"},
                )
        elif tx.type_transaction == TypeTransactionKopar.cotisation:
            if not tx.cotisation_id:
                actions.append("cotisation_id manquant sur tx (skip)")
            else:
                from app.models.paiements import PeriodePaiement

                try:
                    _ = PeriodePaiement.normaliser(tx.periode_mois)
                except Exception:
                    tx.periode_mois = 1
                ref = (
                    f"KOPAR-RECONCILE-{str(tx.id)[:8].upper()}"
                    if not getattr(tx, "kopar_token", None)
                    else (getattr(tx, "kopar_token") or f"KOPAR-RECONCILE-{str(tx.id)[:8].upper()}")
                )
                lignes = await orchestrator.cotisations.mark_paid_periode(
                    tx,
                    reference_paiement=ref,
                    mode_paiement="kopar_reconcile",
                    update_tx_status=True,
                )
                if lignes:
                    annee_mois = [f"{c.annee}-{c.mois:02d}" for c in lignes]
                    actions.append(
                        f"cotisation period={getattr(tx, 'periode_mois') or 1} mois="
                        f"{','.join(annee_mois)} -> {len(lignes)} ligne(s) statut payee"
                    )
                else:
                    if tx.statut == StatutTransactionKopar.success:
                        actions.append(
                            f"cotisation {tx.cotisation_id} -> deja payee (idempotent), tx statut deja success"
                        )
                    else:
                        actions.append(
                            f"cotisation {tx.cotisation_id} -> aucune ligne marquee (possiblement deja payees)"
                        )
                        if tx.statut != StatutTransactionKopar.success:
                            await orchestrator.transactions.update_after_webhook(
                                tx.id,
                                StatutTransactionKopar.success,
                                webhook_body={
                                    "reconcile_job": True,
                                    "method": "kopar_get_transaction_poll",
                                    "note": "aucune ligne cotisation marquee mais tx marquee success",
                                },
                            )
        else:
            actions.append(
                f"type_transaction={tx.type_transaction} sans adhesion_id/cotisation_id valides (mark success seul)"
            )
            tx.statut = StatutTransactionKopar.success
            tx.last_webhook_received_at = datetime.now(timezone.utc)
            if tx.last_webhook_body and isinstance(tx.last_webhook_body, dict):
                body = dict(tx.last_webhook_body)
                body.update({"reconcile_job": True})
                tx.last_webhook_body = body
            else:
                tx.last_webhook_body = {"reconcile_job": True}
    except Exception as exc:
        actions.append(f"ERREUR appels orchestrator / repo: {exc!r}")

    if dry_run:
        pass
    else:
        await db.flush()
    return actions


async def _reconcile_one_tour(*, dry_run: bool, older_minutes_override: int | None = None) -> Tuple[int, int, int]:
    """Un seul passage. Retourne (candidats, marques_success, autres_marques)."""
    settings = get_settings()
    older_minutes = int(older_minutes_override) if older_minutes_override is not None else max(1, int(settings.reconcile_kopar_older_minutes or 5))
    db: AsyncSession
    async with AsyncSessionLocal() as db:
        candidats = await _get_pending_transactions(db, older_minutes)
        _print(
            "INFO",
            f"Tour démarré : {len(candidats)} transaction(s) en statut new/pending "
            f"aged >= {older_minutes} min.",
        )
        if not candidats:
            return 0, 0, 0

        client = KoparClient()
        marques_success = 0
        autres_marques = 0

        for tx in candidats:
            token = str(tx.kopar_token or "").strip()
            if not token:
                _print("WARN", f"tx {tx.id} — kopar_token vide (skip).")
                continue
            try:
                detail = await client.get_transaction_detail(token)
            except KoparError as e:
                _print(
                    "WARN",
                    f"tx {tx.id} KoparError appel detail statut HTTP={e.status_code} "
                    f"kopar_error_code={e.kopar_error_code} — {e}",
                )
                continue
            except Exception as exc:
                _print("ERROR", f"tx {tx.id} exception sur get_transaction_detail : {exc!r}")
                continue

            nouveau = detail.statut
            if nouveau == tx.statut:
                # Aucun changement, on touche à rien.
                continue

            _print(
                "INFO",
                f"tx {tx.id} (token…{token[-6:]}) statut Kopar={nouveau.value} vs BDD={tx.statut.value}",
            )

            if nouveau == StatutTransactionKopar.success:
                actions = await _apply_success_on_business_records(db, tx, dry_run=dry_run)
                marques_success += 1
                for a in actions:
                    _print("OK" if not dry_run else "DRY", f"  → {a}")
            elif nouveau in (
                StatutTransactionKopar.failed,
                StatutTransactionKopar.cancelled,
                StatutTransactionKopar.refunded,
            ):
                autres_marques += 1
                if not dry_run:
                    tx.statut = nouveau
                    tx.last_webhook_received_at = datetime.now(timezone.utc)
                    if tx.last_webhook_body and isinstance(tx.last_webhook_body, dict):
                        body = dict(tx.last_webhook_body)
                        body.update({"reconcile_job": True})
                        tx.last_webhook_body = body
                    else:
                        tx.last_webhook_body = {"reconcile_job": True}
                    await db.flush()
                _print(
                    "INFO" if dry_run else "OK",
                    f"  → statut_final={nouveau.value} (pas de marquage adh/cot)",
                )
            else:
                # pending/new : rien, on retente prochaine boucle
                pass

        if not dry_run:
            await db.commit()

    return len(candidats), marques_success, autres_marques


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
    total_cands, ok, autres = await _reconcile_one_tour(dry_run=dry_run, older_minutes_override=older_minutes)
    duree_ms = int((time.monotonic() - debut) * 1000)
    _print(
        "INFO",
        f"Tour one-shot terminé en {duree_ms}ms. "
        f"Candidats={total_cands} ; marqués SUCCESS={ok} ; autres statuts={autres}.",
    )
    return 0


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
