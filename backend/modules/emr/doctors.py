"""EMR's view of doctors (docs/31_CORE_DOCTOR_SCOPE.md, phase 2).

A doctor is a core `practitioners` record owned by the hospital; EMR works with the ones actively mapped to
THIS clinic (`practitioner_clinics`). Appointments, schedules and prescriptions store `practitioner_id`."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.practitioners import Practitioner, PractitionerClinic


async def get_clinic_doctor(db: AsyncSession, pharmacy_id: uuid.UUID, practitioner_id) -> Practitioner:
    """The doctor, only if they are active and actively mapped to this clinic — else a plain 404, so one
    clinic can never book, schedule or prescribe under another clinic's doctor."""
    try:
        pid = uuid.UUID(str(practitioner_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doc = (await db.execute(
        select(Practitioner).join(PractitionerClinic, PractitionerClinic.practitioner_id == Practitioner.id)
        .where(Practitioner.id == pid, Practitioner.deleted_at.is_(None), Practitioner.is_active.is_(True),
               PractitionerClinic.pharmacy_id == pharmacy_id, PractitionerClinic.is_active.is_(True),
               PractitionerClinic.deleted_at.is_(None)))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doc


async def clinic_doctors(db: AsyncSession, pharmacy_id: uuid.UUID) -> list[tuple[Practitioner, Optional[int]]]:
    """Every active doctor mapped to this clinic, with this clinic's fee, ordered by name."""
    rows = (await db.execute(
        select(Practitioner, PractitionerClinic.consultation_fee_paise)
        .join(PractitionerClinic, PractitionerClinic.practitioner_id == Practitioner.id)
        .where(Practitioner.deleted_at.is_(None), Practitioner.is_active.is_(True),
               PractitionerClinic.pharmacy_id == pharmacy_id, PractitionerClinic.is_active.is_(True),
               PractitionerClinic.deleted_at.is_(None))
        .order_by(Practitioner.name))).all()
    return [(p, fee) for p, fee in rows]


async def doctor_for_record(db: AsyncSession, practitioner_id: uuid.UUID) -> Optional[Practitioner]:
    """A doctor looked up from an id stored on one of this clinic's own records (appointment, prescription,
    schedule). No mapping check on purpose: history must keep showing the doctor's name even after they
    are unmapped or removed."""
    return (await db.execute(select(Practitioner).where(
        Practitioner.id == practitioner_id))).scalar_one_or_none()  # tenant-safe: id from this clinic's own row


async def clinic_fee_paise(db: AsyncSession, pharmacy_id: uuid.UUID, practitioner_id: uuid.UUID) -> Optional[int]:
    return (await db.execute(select(PractitionerClinic.consultation_fee_paise).where(
        PractitionerClinic.practitioner_id == practitioner_id, PractitionerClinic.pharmacy_id == pharmacy_id,
        PractitionerClinic.deleted_at.is_(None)))).scalar_one_or_none()
