"""Doctors as their own records (docs/31_CORE_DOCTOR_SCOPE.md) — separate from logins.

A `Practitioner` is owned by the hospital (entity) and mapped to the clinics where they practise
(`PractitionerClinic`, which also carries the consultation fee because it differs per clinic). A
login (`users`) may optionally be linked via `user_id`. External doctors (referring / visiting,
not on staff) are the same record with `is_external = true`."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy import TIMESTAMP

from database import Base


class Practitioner(Base):
    __tablename__ = "practitioners"
    __table_args__ = (
        Index("idx_practitioners_pharmacy", "pharmacy_id"),
        Index("idx_practitioners_chain", "chain_id"),
        Index("idx_practitioners_name", "pharmacy_id", "name"),
        # A login can be linked to at most one live doctor profile.
        Index("uq_practitioners_user", "user_id", unique=True,
              postgresql_where=text("user_id IS NOT NULL AND deleted_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The workspace. Informational: who may SEE a doctor is decided from the caller's
    # real store grants (resolve_chain_scope_pids), never from a raw chain_id filter.
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"), nullable=False)
    # The clinic this record was created at.
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    specialty: Mapped[Optional[str]] = mapped_column(String(100))
    qualification: Mapped[Optional[str]] = mapped_column(String(200))
    registration_no: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(10))
    email: Mapped[Optional[str]] = mapped_column(String(200))
    is_external: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    hospital: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PractitionerClinic(Base):
    """Which clinic a doctor practises at, and their consultation fee there (integer paise)."""
    __tablename__ = "practitioner_clinics"
    __table_args__ = (
        UniqueConstraint("practitioner_id", "clinic_id", name="uq_practitioner_clinics"),
        Index("idx_practitioner_clinics_clinic", "clinic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("practitioners.id"), nullable=False)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=False)
    consultation_fee_paise: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
