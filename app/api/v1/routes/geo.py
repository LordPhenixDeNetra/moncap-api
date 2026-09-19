from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.geo import GeoRepository
from app.schemas.geo import (
    CommuneOutResponse,
    CommunesResponse,
    DepartementOutResponse,
    DepartementsResponse,
    PaysOutResponse,
    PaysResponse,
    RegionOutResponse,
    RegionsResponse,
)

router = APIRouter(prefix="/geo")


@router.get(
    "/pays",
    response_model=PaysResponse,
    summary="Lister tous les pays",
    description="Retourne la liste des pays. Filtrable par continent.",
)
async def list_pays(continent: str | None = None, db: AsyncSession = Depends(get_db)):
    items = await GeoRepository(db).list_pays(continent=continent)
    return {"data": items}


@router.get(
    "/pays/{pays_id}",
    response_model=PaysOutResponse,
    summary="Récupérer un pays par ID",
    description="Retourne les informations d'un pays spécifique.",
)
async def get_pays(pays_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    item = await GeoRepository(db).get_pays(pays_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pays introuvable")
    return {"data": item}


@router.get(
    "/regions",
    response_model=RegionsResponse,
    summary="Lister toutes les régions",
    description="Retourne la liste complète des régions du Sénégal.",
)
async def list_regions(db: AsyncSession = Depends(get_db)):
    items = await GeoRepository(db).list_regions()
    return {"data": items}


@router.get(
    "/regions/{region_id}",
    response_model=RegionOutResponse,
    summary="Récupérer une région par ID",
    description="Retourne les informations d'une région spécifique.",
)
async def get_region(region_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    item = await GeoRepository(db).get_region(region_id)
    if not item:
        raise HTTPException(status_code=404, detail="Région introuvable")
    return {"data": item}


@router.get(
    "/regions/{region_id}/departements",
    response_model=DepartementsResponse,
    summary="Lister les départements d'une région",
    description="Retourne la liste des départements appartenant à une région spécifique.",
)
async def list_departements(region_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    items = await GeoRepository(db).list_departements(region_id=region_id)
    return {"data": items}


@router.get(
    "/departements/{departement_id}",
    response_model=DepartementOutResponse,
    summary="Récupérer un département par ID",
    description="Retourne les informations d'un département spécifique.",
)
async def get_departement(departement_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    item = await GeoRepository(db).get_departement(departement_id)
    if not item:
        raise HTTPException(status_code=404, detail="Département introuvable")
    return {"data": item}


@router.get(
    "/departements/{departement_id}/communes",
    response_model=CommunesResponse,
    summary="Lister les communes d'un département",
    description="Retourne la liste des communes appartenant à un département spécifique.",
)
async def list_communes(departement_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    items = await GeoRepository(db).list_communes(departement_id=departement_id)
    return {"data": items}


@router.get(
    "/communes/{commune_id}",
    response_model=CommuneOutResponse,
    summary="Récupérer une commune par ID",
    description="Retourne les informations d'une commune spécifique.",
)
async def get_commune(commune_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    item = await GeoRepository(db).get_commune(commune_id)
    if not item:
        raise HTTPException(status_code=404, detail="Commune introuvable")
    return {"data": item}

