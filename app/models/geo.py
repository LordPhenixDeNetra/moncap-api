from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    nom: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    departements: Mapped[list["Departement"]] = relationship(back_populates="region", cascade="all, delete-orphan")


class Departement(Base):
    __tablename__ = "departements"
    __table_args__ = (UniqueConstraint("region_id", "nom", name="uq_departement_region_nom"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("regions.id", ondelete="CASCADE"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    region: Mapped["Region"] = relationship(back_populates="departements")
    communes: Mapped[list["Commune"]] = relationship(back_populates="departement", cascade="all, delete-orphan")


class Commune(Base):
    __tablename__ = "communes"
    __table_args__ = (UniqueConstraint("departement_id", "nom", name="uq_commune_departement_nom"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    departement_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("departements.id", ondelete="CASCADE"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    departement: Mapped["Departement"] = relationship(back_populates="communes")

