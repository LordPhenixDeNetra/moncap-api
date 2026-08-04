from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.enums import AdhesionStatus, EngagementType, PaymentMode


class Adhesion(Base):
    __tablename__ = "adhesions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    nom: Mapped[str] = mapped_column(String(200))
    prenom: Mapped[str] = mapped_column(String(200))
    date_naissance: Mapped[date] = mapped_column(Date)
    lieu_naissance: Mapped[str] = mapped_column(String(200))
    profession: Mapped[str] = mapped_column(String(200))
    tel_mobile: Mapped[str] = mapped_column(String(50))
    tel_fixe: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(320), index=True, unique=True)
    cni: Mapped[str] = mapped_column(String(100), index=True, unique=True)
    carte_electeur: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    carte_pastef: Mapped[str | None] = mapped_column(String(100), nullable=True)

    niveau_etude: Mapped[str | None] = mapped_column(String(200), nullable=True)
    annees_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    biographie: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    est_diaspora: Mapped[bool] = mapped_column(Boolean, server_default="0", index=True)

    region_domicile_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("regions.id"), nullable=True, index=True)
    departement_domicile_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("departements.id"), nullable=True, index=True)
    commune_domicile_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("communes.id"), nullable=True, index=True)

    region_militantisme_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("regions.id"), nullable=True, index=True)
    departement_militantisme_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("departements.id"), nullable=True, index=True)
    commune_militantisme_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("communes.id"), nullable=True)

    pays_domicile_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("pays.id"), nullable=True, index=True)
    ville_domicile: Mapped[str | None] = mapped_column(String(200), nullable=True)

    pays_militantisme_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("pays.id"), nullable=True, index=True)
    ville_militantisme: Mapped[str | None] = mapped_column(String(200), nullable=True)

    region_domicile = relationship("Region", foreign_keys=[region_domicile_id])
    departement_domicile = relationship("Departement", foreign_keys=[departement_domicile_id])
    commune_domicile = relationship("Commune", foreign_keys=[commune_domicile_id])

    region_militantisme = relationship("Region", foreign_keys=[region_militantisme_id])
    departement_militantisme = relationship("Departement", foreign_keys=[departement_militantisme_id])
    commune_militantisme = relationship("Commune", foreign_keys=[commune_militantisme_id])

    pays_domicile = relationship("Pays", foreign_keys=[pays_domicile_id])
    pays_militantisme = relationship("Pays", foreign_keys=[pays_militantisme_id])

    fonction_professionnelle: Mapped[str] = mapped_column(String(200))
    engagement: Mapped[list] = mapped_column(JSON, default=list)
    commissariat: Mapped[str] = mapped_column(String(200), index=True)
    commissariat_scientifique_principal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    commissariat_scientifique_secondaire: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mode_paiement: Mapped[PaymentMode] = mapped_column(
        SAEnum(PaymentMode, name="payment_mode", native_enum=False, validate_strings=True),
    )
    montant_adhesion: Mapped[int] = mapped_column(Integer, server_default="25000")
    paiement_confirme: Mapped[bool] = mapped_column(Boolean, server_default="0")
    reference_paiement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cv_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_recto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_verso_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    statut: Mapped[AdhesionStatus] = mapped_column(
        SAEnum(AdhesionStatus, name="adhesion_status", native_enum=False, validate_strings=True),
        server_default=AdhesionStatus.en_attente.value,
        index=True,
    )
    motif_rejet: Mapped[str | None] = mapped_column(String(500), nullable=True)

    validation_accueil_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    validation_accueil_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validation_accueil_user = relationship(
        "User", foreign_keys=[validation_accueil_user_id]
    )

    validation_directoire_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    validation_directoire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validation_directoire_user = relationship(
        "User", foreign_keys=[validation_directoire_user_id]
    )

    certification: Mapped[bool] = mapped_column(Boolean, server_default="0")

    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
