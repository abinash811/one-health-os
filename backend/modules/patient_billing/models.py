"""Patient Billing tables (docs/29_BILLING_SCOPE.md). Money is integer paise.
No foreign keys into EMR or pharmacy tables — the patient is a plain id plus a
name/UHID snapshot, so this module works with any module that posts charges."""
from __future__ import annotations
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy import TIMESTAMP

from database import Base
from modules.patient_billing.constants import (
    CHG_UNBILLED, INV_ISSUED, SRC_EMR)


class PbInvoice(Base):
    """A numbered, frozen bundle of charges. `lines` is a snapshot, so later
    edits to a charge can never change an issued invoice."""
    __tablename__ = "pb_invoices"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "invoice_number", name="uq_pb_invoices_number"),
        Index("idx_pb_invoices_patient", "pharmacy_id", "patient_id"),
        Index("idx_pb_invoices_status", "pharmacy_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    patient_uhid: Mapped[Optional[str]] = mapped_column(String(30))
    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False)
    counter: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=INV_ISSUED, server_default=INV_ISSUED, nullable=False)
    gross_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    net_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PbChargeItem(Base):
    """One billable line on a patient's account, posted by any module."""
    __tablename__ = "pb_charge_items"
    __table_args__ = (
        # A retried post (same key) never double-charges; keys are never reused, even after a void.
        Index("uq_pb_charge_items_key", "pharmacy_id", "idempotency_key", unique=True,
              postgresql_where=text("idempotency_key IS NOT NULL")),
        Index("idx_pb_charge_items_patient", "pharmacy_id", "patient_id", "status"),
        Index("idx_pb_charge_items_invoice", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    patient_uhid: Mapped[Optional[str]] = mapped_column(String(30))
    source_module: Mapped[str] = mapped_column(String(20), default=SRC_EMR, nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(100))
    encounter_ref: Mapped[Optional[str]] = mapped_column(String(100))
    encounter_type: Mapped[Optional[str]] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=CHG_UNBILLED, server_default=CHG_UNBILLED, nullable=False)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pb_invoices.id"))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(150))
    void_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PbPayment(Base):
    """Money received against one invoice; each has its own receipt number."""
    __tablename__ = "pb_payments"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "receipt_number", name="uq_pb_payments_receipt"),
        Index("idx_pb_payments_invoice", "invoice_id"),
        Index("idx_pb_payments_day", "pharmacy_id", "paid_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pb_invoices.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(100))
    receipt_number: Mapped[str] = mapped_column(String(30), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    received_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
