from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.geo import Commune, Departement, Region


async def seed_geo():
    csv_path = Path("senegal_regions_departements_communes.csv")
    if not csv_path.exists():
        print(f"Fichier {csv_path} introuvable.")
        return

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        async with session.begin():
            print("Début du seed des données géographiques...")

            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                
                regions_cache: dict[str, Region] = {}
                deps_cache: dict[str, Departement] = {}

                # Charger les régions existantes pour éviter les doublons si relancé
                res = await session.execute(select(Region))
                for r in res.scalars():
                    regions_cache[r.nom] = r

                # Charger les départements existants
                res = await session.execute(select(Departement))
                for d in res.scalars():
                    deps_cache[f"{d.region_id}_{d.nom}"] = d

                count_r, count_d, count_c = 0, 0, 0

                for row in reader:
                    r_nom = row["Region"].strip()
                    d_nom = row["Departement"].strip()
                    c_nom = row["Commune"].strip()

                    # Gestion Région
                    if r_nom not in regions_cache:
                        region = Region(nom=r_nom)
                        session.add(region)
                        await session.flush()
                        regions_cache[r_nom] = region
                        count_r += 1
                    
                    region = regions_cache[r_nom]

                    # Gestion Département
                    dep_key = f"{region.id}_{d_nom}"
                    if dep_key not in deps_cache:
                        dep = Departement(nom=d_nom, region_id=region.id)
                        session.add(dep)
                        await session.flush()
                        deps_cache[dep_key] = dep
                        count_d += 1
                    
                    dep = deps_cache[dep_key]

                    # Gestion Commune (on suppose pas de doublons directs dans le CSV pour une même dep)
                    # Pour être sûr, on peut vérifier l'existence
                    res_c = await session.execute(
                        select(Commune).where(Commune.departement_id == dep.id, Commune.nom == c_nom)
                    )
                    if not res_c.scalar_one_or_none():
                        commune = Commune(nom=c_nom, departement_id=dep.id)
                        session.add(commune)
                        count_c += 1

            print(f"Seed terminé : {count_r} régions, {count_d} départements, {count_c} communes ajoutés.")


if __name__ == "__main__":
    asyncio.run(seed_geo())
