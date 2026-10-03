"""Slot/token helpers for EMR appointments: the doctor's open slots, double-booking guard,
walk-in tokens. Shared by the appointments router (docs/28_EMR_SCOPE.md)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from modules.emr.constants import APPT_BOOKED, APPT_CHECKED_IN, APPT_COMPLETED, APPT_IN_CONSULT
from modules.emr.doctors import get_clinic_doctor
from modules.emr.models import EmrAppointment, EmrDoctorSchedule, EmrPatient
from routers.auth_helpers import get_owned_or_404

_LIVE = (APPT_BOOKED, APPT_CHECKED_IN, APPT_IN_CONSULT, APPT_COMPLETED)


async def _slot_grid(db, pharmacy_id, practitioner_id, day: date) -> list[tuple[time, time]]:
    """Every (start, end) slot the doctor works on `day`, from their live schedule blocks."""
    blocks = (await db.execute(select(EmrDoctorSchedule).where(
        EmrDoctorSchedule.pharmacy_id == pharmacy_id,
        EmrDoctorSchedule.practitioner_id == practitioner_id,
        EmrDoctorSchedule.weekday == day.weekday(),
        EmrDoctorSchedule.is_active.is_(True),
        EmrDoctorSchedule.deleted_at.is_(None)))).scalars().all()
    slots = []
    for b in blocks:
        cur = datetime.combine(day, b.start_time)
        stop = datetime.combine(day, b.end_time)
        step = timedelta(minutes=b.slot_minutes)
        while cur + step <= stop:
            slots.append((cur.time(), (cur + step).time()))
            cur += step
    return sorted(slots)


async def _booked_starts(db, pharmacy_id, practitioner_id, day, ignore_id=None) -> set:
    rows = (await db.execute(select(EmrAppointment).where(
        EmrAppointment.pharmacy_id == pharmacy_id,
        EmrAppointment.practitioner_id == practitioner_id,
        EmrAppointment.appointment_date == day,
        EmrAppointment.start_time.is_not(None),
        EmrAppointment.deleted_at.is_(None),
        EmrAppointment.status.in_(_LIVE)))).scalars().all()
    return {r.start_time for r in rows if r.id != ignore_id}


async def _next_token(db, pharmacy_id, practitioner_id, day) -> int:
    top = (await db.execute(select(func.max(EmrAppointment.token_number)).where(
        EmrAppointment.pharmacy_id == pharmacy_id,
        EmrAppointment.practitioner_id == practitioner_id,
        EmrAppointment.appointment_date == day))).scalar()
    return (top or 0) + 1


async def _check_patient_doctor(db, pharmacy_id, patient_id, practitioner_id):
    await get_owned_or_404(
        db, EmrPatient, patient_id, pharmacy_id, not_found_detail="Patient not found",
        extra_conditions=[EmrPatient.deleted_at.is_(None)])
    await get_clinic_doctor(db, pharmacy_id, practitioner_id)


async def _resolve_slot(db, pharmacy_id, practitioner_id, day, start, ignore_id=None):
    """Validates a requested start time against the schedule grid; returns its end time."""
    grid = dict(await _slot_grid(db, pharmacy_id, practitioner_id, day))
    if start not in grid:
        raise HTTPException(
            status_code=422,
            detail="That time is not an open slot in the doctor's schedule for that day")
    if start in await _booked_starts(db, pharmacy_id, practitioner_id, day, ignore_id):
        raise HTTPException(status_code=409, detail="That slot is already booked")
    return grid[start]
