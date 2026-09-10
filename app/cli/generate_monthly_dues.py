from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.paiements import CotisationsService, ParametresPaiementService


async def main():
    parser = argparse.ArgumentParser(
        description="Générer les cotisations mensuelles pour TOUS les adhérents validés (run au 1er du mois)",
    )
    parser.add_argument(
        "--annee",
        type=int,
        default=date.today().year,
        help="Année cible (par défaut: année en cours)",
    )
    parser.add_argument(
        "--mois",
        type=int,
        default=date.today().month,
        help="Mois cible 1-12 (par défaut: mois en cours)",
    )
    parser.add_argument(
        "--seed-defaults",
        action="store_true",
        help="Seed les paramètres paiement par défaut si table vide, PUIS générer les cotisations",
    )
    args = parser.parse_args()

    if not (1 <= args.mois <= 12):
        print(f"ERREUR: mois invalide {args.mois} (doit être 1-12)")
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        if args.seed_defaults:
            ps = ParametresPaiementService(session)
            await ps.seed_defaults_if_empty()
            print("✅ Paramètres paiement vérifiés / seedés.")

        cs = CotisationsService(session)
        total, crees = await cs.generer_tous_les_du_mois(args.annee, args.mois)
        await cs.marquer_echues_du_mois_precedent()
        await session.commit()

    print(f"✅ {crees}/{total} nouvelles cotisations créées pour {args.mois:02d}/{args.annee}.")


if __name__ == "__main__":
    asyncio.run(main())
