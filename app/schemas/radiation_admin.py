from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DisabledReason


class MoisImpayeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    annee: int
    mois: int
    statut: str


class RadiationCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    adhesion_id: uuid.UUID = Field(alias="adhesionId")
    adhesion_nom: str = Field(alias="adhesionNom")
    adhesion_prenom: str = Field(alias="adhesionPrenom")
    email: str
    tel_mobile: str = Field(alias="telMobile")
    user_id: uuid.UUID | None = Field(default=None, alias="userId")
    streak_mois_impayes: int = Field(alias="streakMoisImpayes")
    premier_mois_impaye: tuple[int, int] | None = Field(
        default=None, alias="premierMoisImpaye"
    )
    dernier_mois_impaye: tuple[int, int] | None = Field(
        default=None, alias="dernierMoisImpaye"
    )
    mois_concernes: list[MoisImpayeOut] = Field(
        default_factory=list, alias="moisConcernes"
    )


class RadiationCandidatesResponse(BaseModel):
    data: list[RadiationCandidateOut]
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Infos complémentaires (settings, delai_mois, as_of, total candidats...).",
    )


class ApplyMassiveRadiationRequest(BaseModel):
    adhesion_ids: list[uuid.UUID] = Field(
        default_factory=list,
        alias="adhesionIds",
        description=(
            "Si vide : applique la radiation à TOUS les candidats détectés automatiquement. "
            "Si renseigné : applique uniquement aux ids fournis (vérifie qu'ils sont bien dans la liste des candidats)."
        ),
    )
    motif_override: str | None = Field(
        default=None,
        alias="motifOverride",
        description=(
            "Motif personnalisé. Si vide, un motif générique est utilisé : "
            "\"Radiation automatique — N mois impayés consécutifs.\""
        ),
    )


class RadiationResultItem(BaseModel):
    adhesion_id: uuid.UUID = Field(alias="adhesionId")
    adhesion_nom: str = Field(alias="adhesionNom")
    adhesion_prenom: str = Field(alias="adhesionPrenom")
    statut: str  # "radié" / "erreur"
    erreur: str | None = None


class ApplyMassiveRadiationResponse(BaseModel):
    data: list[RadiationResultItem]
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="total, radiés, erreurs, dry_run=false.",
    )


class RadierManuelRequest(BaseModel):
    motif: str = Field(
        min_length=10,
        max_length=1000,
        description="Motif obligatoire expliquant la radiation manuelle.",
    )


class RehabiliterRequest(BaseModel):
    motif: str = Field(
        min_length=10,
        max_length=1000,
        description="Motif obligatoire expliquant la réhabilitation (régularisation, appel, bonne foi...).",
    )
