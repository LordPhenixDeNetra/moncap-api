from __future__ import annotations

import uuid
from datetime import date
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AdhesionStatus, EngagementType, PaymentMode
from app.schemas.users_out import UserOut


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


class AdminAdhesionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    nom: str
    prenom: str
    email: str
    cni: str
    commissariat: str
    statut: AdhesionStatus
    created_at: datetime = Field(alias="createdAt")

    valide_niveau1_par_user: UserOut | None = Field(default=None, alias="valideNiveau1ParUser")
    valide_niveau1_at: datetime | None = Field(default=None, alias="valideNiveau1At")
    valide_niveau2_par_user: UserOut | None = Field(default=None, alias="valideNiveau2ParUser")
    valide_niveau2_at: datetime | None = Field(default=None, alias="valideNiveau2At")
    rejete_par_user: UserOut | None = Field(default=None, alias="rejeteParUser")
    rejete_at: datetime | None = Field(default=None, alias="rejeteAt")
    en_complement_par_user: UserOut | None = Field(default=None, alias="enComplementParUser")
    en_complement_at: datetime | None = Field(default=None, alias="enComplementAt")
    radie_par_user: UserOut | None = Field(default=None, alias="radieParUser")
    radie_at: datetime | None = Field(default=None, alias="radieAt")
    motif_rejet: str | None = Field(default=None, alias="motifRejet")


class AdminAdhesionListResponse(BaseModel):
    data: list[AdminAdhesionItem]
    meta: PaginationMeta


class AdminUpdateAdhesionRequest(BaseModel):
    statut: AdhesionStatus
    motif_rejet: str | None = Field(default=None, alias="motifRejet")


class AdminConfirmPaymentRequest(BaseModel):
    paiement_confirme: bool = Field(default=True, alias="paiementConfirme")
    reference_paiement: str | None = Field(default=None, alias="referencePaiement")


class AdminUpdateAdhesionInfoRequest(BaseModel):
    nom: str | None = None
    prenom: str | None = None
    date_naissance: date | None = None
    lieu_naissance: str | None = None
    profession: str | None = None
    tel_mobile: str | None = None
    tel_fixe: str | None = None
    email: str | None = None
    cni: str | None = None
    carte_electeur: str | None = None
    carte_pastef: str | None = None

    niveau_etude: str | None = None
    annees_experience: int | None = None
    biographie: str | None = None

    est_diaspora: bool | None = None

    region_domicile_id: uuid.UUID | None = None
    departement_domicile_id: uuid.UUID | None = None
    commune_domicile_id: uuid.UUID | None = None
    region_militantisme_id: uuid.UUID | None = None
    departement_militantisme_id: uuid.UUID | None = None
    commune_militantisme_id: uuid.UUID | None = None

    pays_domicile_id: uuid.UUID | None = None
    ville_domicile: str | None = None
    pays_militantisme_id: uuid.UUID | None = None
    ville_militantisme: str | None = None

    fonction_professionnelle: str | None = None
    engagement: list[EngagementType] | None = None
    commissariat: str | None = None
    commissariat_scientifique_principal: str | None = None
    commissariat_scientifique_secondaire: str | None = None

    mode_paiement: PaymentMode | None = None
    montant_adhesion: int | None = None
    reference_paiement: str | None = None
    certification: bool | None = None


class AdminUpdateAdhesionResponse(BaseModel):
    data: dict
