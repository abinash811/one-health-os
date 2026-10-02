"""EMR step 1 tables: patients, doctor working hours, appointments
(docs/28_EMR_SCOPE.md).

Design decisions (Abinash, Oct 2, 2026):
- `emr_patients` is EMR's own table, not `customers` — EMR must work with
  the pharmacy module switched off. `customer_id` is an optional, soft
  link used only when both modules are on (matched by phone number).
- A doctor is a `users` row (logs in with their own account), not the
  per-pharmacy `doctors` directory, for the same independence reason.
- `pharmacy_id` stays the tenant key (docs/27_PLATFORM_MODULE_MAP.md).
"""
from __future__ import annotations
import uuid
from datetime import date, time
from typing import Optional
from sqlalchemy import (
    Boolean, Date, ForeignKey, Index, Integer, String, Text, Time,
    UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy import TIMESTAMP

from database import Base
from modules.emr.constants import (
    APPT_BOOKED, APPT_TYPE_SCHEDULED, DEFAULT_RX_PREFIX, DEFAULT_SLOT_MINUTES,
    DEFAULT_UHID_DIGITS, DEFAULT_UHID_PREFIX, PATIENT_SOURCE_EMR, RX_DRAFT)


class EmrPatient(Base):
    __tablename__ = "emr_patients"
    __table_args__ = (
        Index("idx_emr_patients_pharmacy", "pharmacy_id"),
        Index("idx_emr_patients_phone", "pharmacy_id", "phone"),
        Index("idx_emr_patients_name", "pharmacy_id", "name"),
        Index("idx_emr_patients_customer", "customer_id"),
        # UHID = the clinic's own patient ID; unique per clinic, never reused.
        Index("uq_emr_patients_uhid", "pharmacy_id", "uhid", unique=True,
              postgresql_where=text("uhid IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    uhid: Mapped[Optional[str]] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(10))
    alternate_phone: Mapped[Optional[str]] = mapped_column(String(10))
    email: Mapped[Optional[str]] = mapped_column(String(200))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    age: Mapped[Optional[int]] = mapped_column(Integer)
    gender: Mapped[Optional[str]] = mapped_column(String(10))
    blood_group: Mapped[Optional[str]] = mapped_column(String(5))
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    allergies: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(
        String(20), default=PATIENT_SOURCE_EMR, server_default=PATIENT_SOURCE_EMR, nullable=False)
    # Soft link to the pharmacy module's customer — plain UUID, no FK, so
    # the EMR schema never depends on a pharmacy table existing.
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EmrDoctorSchedule(Base):
    """One working-hours block for one doctor on one weekday (Mon=0..Sun=6).
    A doctor with morning + evening clinic has two rows for the same day."""
    __tablename__ = "emr_doctor_schedules"
    __table_args__ = (
        Index("idx_emr_doctor_schedules_doctor", "pharmacy_id", "doctor_user_id", "weekday"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    doctor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=15, server_default="15", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EmrAppointment(Base):
    """A visit. `start_time` is NULL for a walk-in (token only). The token
    number is per doctor per day; the unique constraint is the guard against
    two receptionists being handed the same token."""
    __tablename__ = "emr_appointments"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "doctor_user_id", "appointment_date", "token_number",
                         name="uq_emr_appointments_token"),
        # No two live bookings for the same doctor/day/time slot.
        Index("uq_emr_appointments_slot", "pharmacy_id", "doctor_user_id", "appointment_date",
              "start_time", unique=True,
              postgresql_where=text("deleted_at IS NULL AND start_time IS NOT NULL "
                                    "AND status NOT IN ('cancelled', 'no_show')")),
        Index("idx_emr_appointments_day", "pharmacy_id", "appointment_date"),
        Index("idx_emr_appointments_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emr_patients.id"), nullable=False)
    doctor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[Optional[time]] = mapped_column(Time)
    end_time: Mapped[Optional[time]] = mapped_column(Time)
    token_number: Mapped[int] = mapped_column(Integer, nullable=False)
    appointment_type: Mapped[str] = mapped_column(
        String(20), default=APPT_TYPE_SCHEDULED, server_default=APPT_TYPE_SCHEDULED, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=APPT_BOOKED, server_default=APPT_BOOKED, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    checked_in_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EmrPrescription(Base):
    """One prescription per visit — it carries the whole consultation record
    (vitals, complaints, diagnosis, advice, follow-up) plus its medicine lines
    (Abinash, Oct 2, 2026: "all these details should be part of one single
    prescription"). There is deliberately no separate consultation table."""
    __tablename__ = "emr_prescriptions"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "rx_number", name="uq_emr_prescriptions_number"),
        # One live (non-cancelled) Rx per appointment; cancelling frees it for a replacement.
        Index("uq_emr_prescriptions_appointment", "appointment_id", unique=True,
              postgresql_where=text("status <> 'cancelled' AND deleted_at IS NULL")),
        Index("idx_emr_prescriptions_patient", "patient_id"),
        Index("idx_emr_prescriptions_pharmacy", "pharmacy_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emr_appointments.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emr_patients.id"), nullable=False)
    doctor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    rx_number: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=RX_DRAFT, server_default=RX_DRAFT, nullable=False)
    # {"bp_systolic": 120, "bp_diastolic": 80, "pulse": 72, "temperature_c": 37.2,
    #  "spo2": 98, "weight_kg": 64.5} — every key optional.
    vitals: Mapped[Optional[dict]] = mapped_column(JSONB)
    complaints: Mapped[Optional[str]] = mapped_column(Text)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    advice: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date)
    issued_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EmrPrescriptionItem(Base):
    """One medicine line on a prescription. `medicine_name` is free text so EMR
    works without the pharmacy module."""
    __tablename__ = "emr_prescription_items"
    __table_args__ = (
        Index("idx_emr_prescription_items_rx", "prescription_id"),
        Index("idx_emr_prescription_items_name", "pharmacy_id", "medicine_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emr_prescriptions.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    medicine_name: Mapped[str] = mapped_column(String(300), nullable=False)
    dosage: Mapped[Optional[str]] = mapped_column(String(100))
    frequency: Mapped[Optional[str]] = mapped_column(String(100))
    duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    instructions: Mapped[Optional[str]] = mapped_column(String(300))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class EmrSettings(Base):
    """One row per clinic: print identity, ID formats and the patient-form
    layout. Created on first read with defaults, so a clinic never has to
    configure anything before using EMR."""
    __tablename__ = "emr_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False, unique=True)
    # Blank = fall back to the pharmacy's own name / address / phone on printouts.
    clinic_name: Mapped[Optional[str]] = mapped_column(String(200))
    clinic_address: Mapped[Optional[str]] = mapped_column(Text)
    clinic_phone: Mapped[Optional[str]] = mapped_column(String(20))
    clinic_email: Mapped[Optional[str]] = mapped_column(String(200))
    registration_no: Mapped[Optional[str]] = mapped_column(String(100))
    rx_footer: Mapped[Optional[str]] = mapped_column(Text)
    rx_prefix: Mapped[str] = mapped_column(
        String(10), default=DEFAULT_RX_PREFIX, server_default=DEFAULT_RX_PREFIX, nullable=False)
    uhid_prefix: Mapped[str] = mapped_column(
        String(10), default=DEFAULT_UHID_PREFIX, server_default=DEFAULT_UHID_PREFIX, nullable=False)
    uhid_digits: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_UHID_DIGITS, server_default=str(DEFAULT_UHID_DIGITS), nullable=False)
    # Next number to hand out — advanced atomically at registration, never edited by hand.
    uhid_next: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    default_slot_minutes: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_SLOT_MINUTES, server_default=str(DEFAULT_SLOT_MINUTES), nullable=False)
    # {"allergies": "required", "blood_group": "hidden", ...} — missing keys use PATIENT_FORM_DEFAULTS.
    patient_form: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EmrDoctorProfile(Base):
    """Professional details printed on a doctor's prescriptions. The doctor
    themself is still just a `users` row."""
    __tablename__ = "emr_doctor_profiles"
    __table_args__ = (UniqueConstraint("pharmacy_id", "user_id", name="uq_emr_doctor_profiles_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    specialty: Mapped[Optional[str]] = mapped_column(String(100))
    qualification: Mapped[Optional[str]] = mapped_column(String(200))
    registration_no: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
