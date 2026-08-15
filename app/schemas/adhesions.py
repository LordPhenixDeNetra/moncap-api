from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.urls import to_absolute_public_url
from app.models.enums import AdhesionStatus, EngagementType, PaymentMode
from app.schemas.geo import CommuneOut, DepartementOut, PaysOut, RegionOut


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

    niveau_etude: str | None = None
    annees_experience: int | None = None
    biographie: str | None = None

    est_diaspora: bool = False

    region_domicile_id: uuid.UUID | None = None
    departement_domicile_id: uuid.UUID | None = None
    commune_domicile_id: uuid.UUID | None = None
    region_militantisme_id: uuid.UUID | None = None
    departement_militantisme_id: uuid.UUID | None = None
    commune_militantisme_id: uuid.UUID | None = None

    region_domicile: RegionOut | None = None
    departement_domicile: DepartementOut | None = None
    commune_domicile: CommuneOut | None = None
    region_militantisme: RegionOut | None = None
    departement_militantisme: DepartementOut | None = None
    commune_militantisme: CommuneOut | None = None

    pays_domicile_id: uuid.UUID | None = None
    ville_domicile: str | None = None
    pays_militantisme_id: uuid.UUID | None = None
    ville_militantisme: str | None = None

    pays_domicile: PaysOut | None = None
    pays_militantisme: PaysOut | None = None

    fonction_professionnelle: str
    engagement: list[EngagementType]
    commissariat: str
    commissariat_scientifique_principal: str | None = None
    commissariat_scientifique_secondaire: str | None = None
    mode_paiement: PaymentMode
    montant_adhesion: int
    paiement_confirme: bool
    reference_paiement: str | None
    cv_url: str | None
    photo_recto_url: str | None
    photo_verso_url: str | None
    profile_photo_url: str | None = None
    statut: AdhesionStatus
    motif_rejet: str | None = Field(default=None, alias="motifRejet")
    certification: bool
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_serializer("cv_url", "photo_recto_url", "photo_verso_url", "profile_photo_url")
    def _abs_file_urls(self, v: str | None) -> str | None:
        return to_absolute_public_url(v)


class AdhesionDetailResponse(BaseModel):
    data: AdhesionDetailOut
