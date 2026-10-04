"""Clinic settings helpers: get-or-create the per-clinic row, and hand out
UHIDs. Shared by the settings, patients and prescriptions routers."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.emr.constants import PATIENT_FORM_DEFAULTS
from modules.emr.models import EmrPatient, EmrSettings


async def get_or_create_settings(db: AsyncSession, clinic_id: uuid.UUID) -> EmrSettings:
    """The clinic's settings row, created with defaults on first use. Two requests creating it
    at once is safe: the loser's savepoint fails on the unique clinic_id and re-reads."""
    row = (await db.execute(select(EmrSettings).where(EmrSettings.clinic_id == clinic_id))).scalar_one_or_none()
    if row:
        return row
    # Existing patients already hold UHIDs from the migration backfill — continue after them.
    existing = (await db.execute(select(func.count()).select_from(EmrPatient).where(
        EmrPatient.clinic_id == clinic_id))).scalar() or 0
    try:
        async with db.begin_nested():
            row = EmrSettings(clinic_id=clinic_id, uhid_next=existing + 1)
            db.add(row)
            await db.flush()
        await db.refresh(row)
        return row
    except IntegrityError:
        return (await db.execute(select(EmrSettings).where(EmrSettings.clinic_id == clinic_id))).scalar_one()


def effective_patient_form(settings: EmrSettings) -> dict:
    return {**PATIENT_FORM_DEFAULTS, **(settings.patient_form or {})}


async def next_uhid(db: AsyncSession, clinic_id: uuid.UUID) -> str:
    """Atomically takes the next UHID (a single UPDATE ... RETURNING, so two simultaneous
    registrations can never get the same number)."""
    await get_or_create_settings(db, clinic_id)
    prefix, digits, taken = (await db.execute(
        update(EmrSettings).where(EmrSettings.clinic_id == clinic_id)
        .values(uhid_next=EmrSettings.uhid_next + 1)
        .returning(EmrSettings.uhid_prefix, EmrSettings.uhid_digits, EmrSettings.uhid_next - 1))).one()
    return f"{prefix}{str(taken).zfill(digits)}"
