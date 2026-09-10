from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.paiements import (
    CotisationStatut,
    ParametrePaiementCode,
    StatutTransactionKopar,
    TypeTransactionKopar,
)

class ParametrePaiementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    code: str
    libelle: str
    montant_fcfa: int | None = None
    valeur_texte: str | None = None
    devise: str = "XOF"
    date_effet: date = Field(alias="dateEffet")
    date_fin_effet: date | None = Field(default=None, alias="dateFinEffet")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ParametrePaiementCreate(BaseModel):
    code: ParametrePaiementCode | str
    libelle: str
    montant_fcfa: int | None = None
    valeur_texte: str | None = None
    devise: str = "XOF"
    date_effet: date
    date_fin_effet: date | None = None


class ParametrePaiementUpdate(BaseModel):
    libelle: str | None = None
    montant_fcfa: int | None = None
    valeur_texte: str | None = None
    devise: str | None = None
    date_effet: date | None = None
    date_fin_effet: date | None = None


class ParametresPaiementListResponse(BaseModel):
    data: list[ParametrePaiementOut]


class CotisationMensuelleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    adhesion_id: uuid.UUID = Field(alias="adhesionId")
    annee: int
    mois: int
    montant: int
    devise: str = "XOF"
    statut: CotisationStatut
    paiement_date: datetime | None = Field(default=None, alias="paiementDate")
    mode_paiement: str | None = Field(default=None, alias="modePaiement")
    reference_paiement: str | None = Field(default=None, alias="referencePaiement")
    paiement_manuel: bool = Field(default=False, alias="paiementManuel")
    paiement_manuel_note: str | None = Field(default=None, alias="paiementManuelNote")
    relance_envoyee_1: bool = Field(default=False, alias="relanceEnvoyee1")
    relance_envoyee_2: bool = Field(default=False, alias="relanceEnvoyee2")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class CotisationDetailOut(CotisationMensuelleOut):
    adhesion_nom: str | None = Field(default=None, alias="adhesionNom")
    adhesion_prenom: str | None = Field(default=None, alias="adhesionPrenom")
    adhesion_email: str | None = Field(default=None, alias="adhesionEmail")
    adhesion_tel_mobile: str | None = Field(default=None, alias="adhesionTelMobile")
    adhesion_commissariat: str | None = Field(default=None, alias="adhesionCommissariat")


class CotisationListResponse(BaseModel):
    data: list[CotisationMensuelleOut]
    total: int | None = None


class CotisationDetailListResponse(BaseModel):
    data: list[CotisationDetailOut]
    total: int | None = None
    payes: int | None = None
    impayes: int | None = None


class PaiementManuelRequest(BaseModel):
    note: str | None = None
    reference_paiement: str | None = Field(default=None, alias="referencePaiement")


class InitPaiementAdhesionPublicRequest(BaseModel):
    email: str
    prenom: str | None = None
    nom: str | None = None
    telephone: str | None = None
    cni: str | None = None
    date_naissance: date | None = Field(default=None, alias="dateNaissance")
    lieu_naissance: str | None = Field(default=None, alias="lieuNaissance")
    service_paiement: str | None = Field(default=None, alias="servicePaiement")


class InitPaiementResponse(BaseModel):
    kopar_token: str = Field(alias="koparToken")
    payment_url: str | None = Field(default=None, alias="paymentUrl")
    qr_code: str | None = Field(default=None, alias="qrCode")
    montant: int
    devise: str


class TransactionKoparOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    kopar_token: str = Field(alias="koparToken")
    kopar_id: str | None = Field(default=None, alias="koparId")
    type_transaction: TypeTransactionKopar = Field(alias="typeTransaction")
    adhesion_id: uuid.UUID | None = Field(default=None, alias="adhesionId")
    cotisation_id: uuid.UUID | None = Field(default=None, alias="cotisationId")
    command_ref: str = Field(alias="commandRef")
    command_name: str = Field(alias="commandName")
    montant: int
    devise: str
    statut: StatutTransactionKopar
    service: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    last_webhook_received_at: datetime | None = Field(
        default=None, alias="lastWebhookAt"
    )
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class TransactionKoparListResponse(BaseModel):
    data: list[TransactionKoparOut]


class AdherentEtatCotisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    adhesion_id: uuid.UUID = Field(alias="adhesionId")
    nom: str
    prenom: str
    qr_url: str = Field(alias="qrUrl")
    cotisation_courante: CotisationMensuelleOut | None = Field(
        default=None, alias="cotisationCourante"
    )
    montant_du: int = Field(default=0, alias="montantDu")
    montant_annuel_paye: int = Field(default=0, alias="montantAnnuelPaye")
    mois_payes_annee: int = Field(default=0, alias="moisPayesAnnee")
