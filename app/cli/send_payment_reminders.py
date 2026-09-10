from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.models.enums import AdhesionStatus
from app.repositories.adhesions import AdhesionRepository
from app.services.adhesion_mail_templates import (
    build_notification_cotisation_mois_disponible,
    build_relance_cotisation_impayee,
)
from app.services.mail import send_email_best_effort
from app.services.paiements import CotisationsService
from app.services.qr_code import QRCodeStorageService


NOMS_MOIS = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


async def envoyer_notifications_debut_mois(annee: int, mois: int, dry_run: bool) -> tuple[int, int]:
    """Notifie TOUS les adhérents (ayant une cotisation en_attente pour ce mois) du début de mois."""
    qr = QRCodeStorageService()
    settings = get_settings()
    total = 0
    envoyes = 0
    async with AsyncSessionLocal() as session:
        cs = CotisationsService(session)
        repo = cs.repo
        adhesion_repo = AdhesionRepository(session)
        ids = await repo.list_ids_impayes_mois(annee, mois, limit=100_000)
        for cid in ids:
            c = await repo.get_by_id(cid)
            if not c:
                continue
            adh = await adhesion_repo.get_by_id(c.adhesion_id)
            if not adh or not adh.email:
                continue
            _, qr_url = qr.generer_qr_adherent(adh.id)
            subject, text, html = build_notification_cotisation_mois_disponible(
                adhesion=adh,
                base_url=settings.public_base_url or settings.api_base_url or "",
                annee=annee,
                mois=mois,
                montant=c.montant,
                qr_url=qr_url,
            )
            total += 1
            if dry_run:
                continue
            ok = send_email_best_effort(
                to=adh.email,
                subject=subject,
                text=text,
                html=html,
                settings=settings,
            )
            if ok:
                await repo.mark_relance_envoyee(cid, 1)
                envoyes += 1
        await session.commit()
    return total, envoyes


async def envoyer_relances(
    annee: int,
    mois: int,
    niveau: int,
    dry_run: bool,
) -> tuple[int, int]:
    if niveau not in (1, 2):
        print(f"ERREUR: niveau {niveau} invalide (1 ou 2)")
        sys.exit(1)
    qr = QRCodeStorageService()
    settings = get_settings()
    total = 0
    envoyes = 0
    async with AsyncSessionLocal() as session:
        cs = CotisationsService(session)
        repo = cs.repo
        adhesion_repo = AdhesionRepository(session)
        only_flag_1 = (niveau == 1)
        only_flag_2 = (niveau == 2)
        ids = await repo.list_ids_impayes_mois(
            annee, mois,
            only_not_relance_1=only_flag_1,
            only_not_relance_2=only_flag_2,
            limit=100_000,
        )
        for cid in ids:
            c = await repo.get_by_id(cid)
            if not c:
                continue
            adh = await adhesion_repo.get_by_id(c.adhesion_id)
            if not adh or not adh.email:
                continue
            _, qr_url = qr.generer_qr_adherent(adh.id)
            subject, text, html = build_relance_cotisation_impayee(
                adhesion=adh,
                base_url=settings.public_base_url or settings.api_base_url or "",
                annee=annee,
                mois=mois,
                montant=c.montant,
                niveau=niveau,
                qr_url=qr_url,
            )
            total += 1
            if dry_run:
                continue
            ok = send_email_best_effort(
                to=adh.email,
                subject=subject,
                text=text,
                html=html,
                settings=settings,
            )
            if ok:
                await repo.mark_relance_envoyee(cid, niveau)
                envoyes += 1
        await session.commit()
    return total, envoyes


async def main():
    parser = argparse.ArgumentParser(
        description="Envoyer emails de début de mois ou relances pour cotisations impayées",
    )
    parser.add_argument(
        "action",
        choices=["debut_mois", "relance"],
        help="debut_mois = notification du 1er ; relance = rappel aux impayés",
    )
    parser.add_argument("--annee", type=int, default=date.today().year)
    parser.add_argument("--mois", type=int, default=date.today().month)
    parser.add_argument(
        "--niveau",
        type=int,
        default=1,
        help="Niveau relance : 1 = premier rappel (jour 10), 2 = dernier rappel (jour 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne pas envoyer d'emails, juste afficher le nombre d'envois prévus",
    )
    args = parser.parse_args()

    if not (1 <= args.mois <= 12):
        print(f"ERREUR: mois invalide {args.mois}")
        sys.exit(1)

    settings = get_settings()
    if not settings.mail_enabled and not args.dry_run:
        print("⚠️  MAIL_ENABLED=false — aucun email ne sera envoyé. Passez --dry-run pour compter ou activez MAIL_ENABLED.")

    if args.action == "debut_mois":
        total, envoyes = await envoyer_notifications_debut_mois(args.annee, args.mois, args.dry_run)
    else:
        total, envoyes = await envoyer_relances(args.annee, args.mois, args.niveau, args.dry_run)

    if args.dry_run:
        print(f"[DRY RUN] Prévu pour {NOMS_MOIS[args.mois]} {args.annee} : {total} emails (action={args.action})")
    else:
        print(f"✅ {envoyes}/{total} emails envoyés pour {NOMS_MOIS[args.mois]} {args.annee} (action={args.action}).")


if __name__ == "__main__":
    asyncio.run(main())
