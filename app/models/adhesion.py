from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
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
    email: Mapped[str] = mapped_column(String(320), index=True)
    cni: Mapped[str] = mapped_column(String(100), index=True)
    carte_electeur: Mapped[str | None] = mapped_column(String(100), nullable=True)
    carte_pastef: Mapped[str | None] = mapped_column(String(100), nullable=True)

    region_domicile_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("regions.id"), index=True)
    departement_domicile_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("departements.id"), index=True)
    commune_domicile_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("communes.id"), index=True)

    region_militantisme_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("regions.id"), index=True)
    departement_militantisme_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("departements.id"), index=True)
    commune_militantisme_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("communes.id"), nullable=True)

    region_domicile = relationship("Region", foreign_keys=[region_domicile_id])
    departement_domicile = relationship("Departement", foreign_keys=[departement_domicile_id])
    commune_domicile = relationship("Commune", foreign_keys=[commune_domicile_id])

    region_militantisme = relationship("Region", foreign_keys=[region_militantisme_id])
    departement_militantisme = relationship("Departement", foreign_keys=[departement_militantisme_id])
    commune_militantisme = relationship("Commune", foreign_keys=[commune_militantisme_id])

    fonction_professionnelle: Mapped[str] = mapped_column(String(200))
    engagement: Mapped[EngagementType] = mapped_column(
        SAEnum(EngagementType, name="engagement_type", native_enum=False, validate_strings=True),
    )
    commissariat: Mapped[str] = mapped_column(String(200), index=True)
    mode_paiement: Mapped[PaymentMode] = mapped_column(
        SAEnum(PaymentMode, name="payment_mode", native_enum=False, validate_strings=True),
    )
    montant_adhesion: Mapped[int] = mapped_column(Integer, server_default="25000")
    paiement_confirme: Mapped[bool] = mapped_column(Boolean, server_default="0")
    reference_paiement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cv_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    statut: Mapped[AdhesionStatus] = mapped_column(
        SAEnum(AdhesionStatus, name="adhesion_status", native_enum=False, validate_strings=True),
        server_default=AdhesionStatus.en_attente.value,
        index=True,
    )
    motif_rejet: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certification: Mapped[bool] = mapped_column(Boolean, server_default="0")

    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
