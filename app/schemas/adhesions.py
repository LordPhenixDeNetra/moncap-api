from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AdhesionStatus, EngagementType, PaymentMode
from app.schemas.geo import CommuneOut, DepartementOut, RegionOut


class AdhesionCreatedData(BaseModel):
    id: uuid.UUID
    statut: AdhesionStatus
    created_at: datetime = Field(alias="createdAt")


class AdhesionCreatedResponse(BaseModel):
    data: AdhesionCreatedData


class AdhesionPublicItem(BaseModel):
    id: uuid.UUID
    statut: AdhesionStatus
    created_at: datetime = Field(alias="createdAt")
    motif_rejet: str | None = Field(default=None, alias="motifRejet")


class AdhesionPublicListResponse(BaseModel):
    data: list[AdhesionPublicItem]


class AdhesionDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    nom: str
    prenom: str
    date_naissance: date
    lieu_naissance: str
    profession: str
    tel_mobile: str
    tel_fixe: str | None
    email: str
    cni: str
    carte_electeur: str | None
    carte_pastef: str | None

    region_domicile_id: uuid.UUID
    departement_domicile_id: uuid.UUID
    commune_domicile_id: uuid.UUID
    region_militantisme_id: uuid.UUID
    departement_militantisme_id: uuid.UUID
    commune_militantisme_id: uuid.UUID | None

    region_domicile: RegionOut | None = None
    departement_domicile: DepartementOut | None = None
    commune_domicile: CommuneOut | None = None
    region_militantisme: RegionOut | None = None
    departement_militantisme: DepartementOut | None = None
    commune_militantisme: CommuneOut | None = None

    fonction_professionnelle: str
    engagement: EngagementType
    commissariat: str
    mode_paiement: PaymentMode
    montant_adhesion: int
    paiement_confirme: bool
    reference_paiement: str | None
    cv_url: str | None
    photo_recto_url: str | None
    photo_verso_url: str | None
    statut: AdhesionStatus
    motif_rejet: str | None = Field(default=None, alias="motifRejet")
    certification: bool
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AdhesionDetailResponse(BaseModel):
    data: AdhesionDetailOut
