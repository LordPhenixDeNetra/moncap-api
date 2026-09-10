from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID


class ParametrePaiementCode(StrEnum):
    adhesion_initiale = "adhesion_initiale"
    cotisation_mensuelle = "cotisation_mensuelle"
    regle_date_premiere_cotisation = "regle_date_premiere_cotisation"


class CotisationStatut(StrEnum):
    en_attente = "en_attente"
    payee = "payee"
    echue = "echue"
    annulee = "annulee"


class TypeTransactionKopar(StrEnum):
    adhesion = "adhesion"
    cotisation = "cotisation"
    autre = "autre"


class StatutTransactionKopar(StrEnum):
    new = "new"
    pending = "pending"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"
    refunded = "refunded"


class ParametrePaiement(Base):
    __tablename__ = "parametres_paiement"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), index=True)
    libelle: Mapped[str] = mapped_column(String(300))
    montant_fcfa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valeur_texte: Mapped[str | None] = mapped_column(String(500), nullable=True)
    devise: Mapped[str] = mapped_column(String(10), server_default="XOF")
    date_effet: Mapped[date] = mapped_column(Date, index=True)
    date_fin_effet: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CotisationMensuelle(Base):
    __tablename__ = "cotisations_mensuelles"
    __table_args__ = (
        UniqueConstraint(
            "adhesion_id", "annee", "mois", name="uq_cotisation_adherent_annee_mois"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    adhesion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("adhesions.id", ondelete="CASCADE"), index=True
    )
    annee: Mapped[int] = mapped_column(Integer, index=True)
    mois: Mapped[int] = mapped_column(Integer, index=True)
    montant: Mapped[int] = mapped_column(Integer)
    devise: Mapped[str] = mapped_column(String(10), server_default="XOF")
    statut: Mapped[CotisationStatut] = mapped_column(
        SAEnum(
            CotisationStatut,
            name="cotisation_statut",
            native_enum=False,
            validate_strings=True,
        ),
        server_default=CotisationStatut.en_attente.value,
        index=True,
    )
    paiement_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mode_paiement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_paiement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    paiement_manuel: Mapped[bool] = mapped_column(Boolean, server_default="0")
    paiement_manuel_par_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    paiement_manuel_note: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    relance_envoyee_1: Mapped[bool] = mapped_column(Boolean, server_default="0")
    relance_envoyee_2: Mapped[bool] = mapped_column(Boolean, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    adhesion = relationship("Adhesion", foreign_keys=[adhesion_id])
    paiement_manuel_par_user = relationship(
        "User", foreign_keys=[paiement_manuel_par_user_id]
    )


class TransactionKopar(Base):
    __tablename__ = "transactions_kopar"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    kopar_token: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    kopar_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    type_transaction: Mapped[TypeTransactionKopar] = mapped_column(
        SAEnum(
            TypeTransactionKopar,
            name="type_transaction_kopar",
            native_enum=False,
            validate_strings=True,
        ),
        index=True,
    )
    adhesion_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("adhesions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cotisation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("cotisations_mensuelles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    command_ref: Mapped[str] = mapped_column(String(200), index=True)
    command_name: Mapped[str] = mapped_column(String(300))
    montant: Mapped[int] = mapped_column(Integer)
    devise: Mapped[str] = mapped_column(String(10), server_default="XOF")
    statut: Mapped[StatutTransactionKopar] = mapped_column(
        SAEnum(
            StatutTransactionKopar,
            name="statut_transaction_kopar",
            native_enum=False,
            validate_strings=True,
        ),
        server_default=StatutTransactionKopar.new.value,
        index=True,
    )
    service: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_first_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_last_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ipn_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    success_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_request: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_webhook_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_webhook_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    statut_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    adhesion = relationship("Adhesion", foreign_keys=[adhesion_id])
    cotisation = relationship("CotisationMensuelle", foreign_keys=[cotisation_id])
