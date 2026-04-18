from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.geo import GeoRepository
from app.schemas.geo import CommunesResponse, DepartementsResponse, RegionsResponse

router = APIRouter(prefix="/geo")


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
    "/regions/{region_id}/departements",
    response_model=DepartementsResponse,
    summary="Lister les départements d'une région",
    description="Retourne la liste des départements appartenant à une région spécifique.",
)
async def list_departements(region_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    items = await GeoRepository(db).list_departements(region_id=region_id)
    return {"data": items}


@router.get(
    "/departements/{departement_id}/communes",
    response_model=CommunesResponse,
    summary="Lister les communes d'un département",
    description="Retourne la liste des communes appartenant à un département spécifique.",
)
async def list_communes(departement_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    items = await GeoRepository(db).list_communes(departement_id=departement_id)
    return {"data": items}

