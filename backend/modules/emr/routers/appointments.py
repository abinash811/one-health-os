"""EMR appointments + today's queue (docs/28_EMR_SCOPE.md).
Scheduled visits must land on a doctor's working-hours slot; walk-ins just
take the next token for today."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_db
from models.users import User as UserORM
from modules.emr.common import _client_ip, _record_audit, _require_emr_permission
from modules.emr.constants import (
    APPOINTMENT_TRANSITIONS, APPT_BOOKED, APPT_CANCELLED, APPT_CHECKED_IN, APPT_COMPLETED,
    APPT_IN_CONSULT, APPT_TYPE_SCHEDULED, APPT_TYPE_WALK_IN)
from modules.emr.models import EmrAppointment, EmrDoctorSchedule, EmrPatient
from routers.auth_helpers import User, get_current_user, get_owned_or_404

router = APIRouter(prefix="/api/emr", tags=["emr-appointments"])

_LIVE = (APPT_BOOKED, APPT_CHECKED_IN, APPT_IN_CONSULT, APPT_COMPLETED)


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    doctor_user_id: uuid.UUID
    appointment_date: date
    start_time: Optional[time] = None   # omitted = walk-in
    reason: Optional[str] = None


class StatusChange(BaseModel):
    status: str
    cancel_reason: Optional[str] = None


def _appt_response(a: EmrAppointment, patient_name=None, doctor_name=None) -> dict:
    fmt = lambda t: t.strftime("%H:%M") if t else None  # noqa: E731
    return {
        "id": str(a.id), "patient_id": str(a.patient_id), "patient_name": patient_name,
        "doctor_user_id": str(a.doctor_user_id), "doctor_name": doctor_name,
        "appointment_date": a.appointment_date.isoformat(),
        "start_time": fmt(a.start_time), "end_time": fmt(a.end_time),
        "token_number": a.token_number, "appointment_type": a.appointment_type,
        "status": a.status, "reason": a.reason, "cancel_reason": a.cancel_reason,
        "checked_in_at": a.checked_in_at.isoformat() if a.checked_in_at else None,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
    }


async def _names(db, a: EmrAppointment):
    """Patient and doctor display names, both re-scoped to the appointment's own pharmacy."""
    p = (await db.execute(select(EmrPatient.name).where(
        EmrPatient.id == a.patient_id, EmrPatient.pharmacy_id == a.pharmacy_id))).scalar()
    d = (await db.execute(select(UserORM.name).where(
        UserORM.id == a.doctor_user_id, UserORM.pharmacy_id == a.pharmacy_id))).scalar()
    return p, d


async def _slot_grid(db, pharmacy_id, doctor_user_id, day: date) -> list[tuple[time, time]]:
    """Every (start, end) slot the doctor works on `day`, from their live schedule blocks."""
    blocks = (await db.execute(select(EmrDoctorSchedule).where(
        EmrDoctorSchedule.pharmacy_id == pharmacy_id,
        EmrDoctorSchedule.doctor_user_id == doctor_user_id,
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


async def _booked_starts(db, pharmacy_id, doctor_user_id, day, ignore_id=None) -> set:
    rows = (await db.execute(select(EmrAppointment).where(
        EmrAppointment.pharmacy_id == pharmacy_id,
        EmrAppointment.doctor_user_id == doctor_user_id,
        EmrAppointment.appointment_date == day,
        EmrAppointment.start_time.is_not(None),
        EmrAppointment.deleted_at.is_(None),
        EmrAppointment.status.in_(_LIVE)))).scalars().all()
    return {r.start_time for r in rows if r.id != ignore_id}


async def _next_token(db, pharmacy_id, doctor_user_id, day) -> int:
    top = (await db.execute(select(func.max(EmrAppointment.token_number)).where(
        EmrAppointment.pharmacy_id == pharmacy_id,
        EmrAppointment.doctor_user_id == doctor_user_id,
        EmrAppointment.appointment_date == day))).scalar()
    return (top or 0) + 1


async def _check_patient_doctor(db, pharmacy_id, patient_id, doctor_user_id):
    await get_owned_or_404(
        db, EmrPatient, patient_id, pharmacy_id, not_found_detail="Patient not found",
        extra_conditions=[EmrPatient.deleted_at.is_(None)])
    await get_owned_or_404(
        db, UserORM, doctor_user_id, pharmacy_id, not_found_detail="Doctor not found",
        extra_conditions=[UserORM.is_active.is_(True)])


async def _resolve_slot(db, pharmacy_id, doctor_user_id, day, start, ignore_id=None):
    """Validates a requested start time against the schedule grid; returns its end time."""
    grid = dict(await _slot_grid(db, pharmacy_id, doctor_user_id, day))
    if start not in grid:
        raise HTTPException(
            status_code=422,
            detail="That time is not an open slot in the doctor's schedule for that day")
    if start in await _booked_starts(db, pharmacy_id, doctor_user_id, day, ignore_id):
        raise HTTPException(status_code=409, detail="That slot is already booked")
    return grid[start]


@router.get("/slots")
async def available_slots(doctor_user_id: uuid.UUID, on_date: date = Query(..., alias="date"),
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "appointments:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    grid = await _slot_grid(db, pharmacy_id, doctor_user_id, on_date)
    taken = await _booked_starts(db, pharmacy_id, doctor_user_id, on_date)
    return [{"start_time": s.strftime("%H:%M"), "end_time": e.strftime("%H:%M"),
             "available": s not in taken} for s, e in grid]


@router.post("/appointments")
async def create_appointment(data: AppointmentCreate, request: Request,
                             current_user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "appointments:create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    if data.appointment_date < date.today():
        raise HTTPException(status_code=422, detail="Cannot book an appointment in the past")
    await _check_patient_doctor(db, pharmacy_id, data.patient_id, data.doctor_user_id)

    end_time = None
    if data.start_time is None:
        if data.appointment_date != date.today():
            raise HTTPException(status_code=422, detail="A walk-in can only be added for today")
        appt_type = APPT_TYPE_WALK_IN
    else:
        appt_type = APPT_TYPE_SCHEDULED
        end_time = await _resolve_slot(
            db, pharmacy_id, data.doctor_user_id, data.appointment_date, data.start_time)

    appt = EmrAppointment(
        pharmacy_id=pharmacy_id, patient_id=data.patient_id, doctor_user_id=data.doctor_user_id,
        appointment_date=data.appointment_date, start_time=data.start_time, end_time=end_time,
        token_number=await _next_token(
            db, pharmacy_id, data.doctor_user_id, data.appointment_date),
        appointment_type=appt_type, reason=data.reason, created_by=uuid.UUID(current_user.id))
    db.add(appt)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Someone just booked that slot or token — please try again")
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "emr_appointment", appt.id,
        _appt_response(appt), db, ip_address=_client_ip(request))
    return _appt_response(appt, *await _names(db, appt))


@router.get("/appointments")
async def list_appointments(
    on_date: Optional[date] = Query(None, alias="date"), doctor_user_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None, status: Optional[str] = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """The day view / live queue. Defaults to today; ordered by token."""
    await _require_emr_permission(current_user, "appointments:view", db)
    query = (
        select(EmrAppointment, EmrPatient.name, UserORM.name)
        .join(EmrPatient, EmrPatient.id == EmrAppointment.patient_id)
        .join(UserORM, UserORM.id == EmrAppointment.doctor_user_id)
        .where(EmrAppointment.pharmacy_id == uuid.UUID(current_user.pharmacy_id),
               EmrAppointment.deleted_at.is_(None)))
    if on_date:
        query = query.where(EmrAppointment.appointment_date == on_date)
    elif not patient_id:
        query = query.where(EmrAppointment.appointment_date == date.today())
    if patient_id:
        query = query.where(EmrAppointment.patient_id == patient_id)
    if doctor_user_id:
        query = query.where(EmrAppointment.doctor_user_id == doctor_user_id)
    if status:
        query = query.where(EmrAppointment.status == status)
    rows = (await db.execute(query.order_by(
        EmrAppointment.appointment_date.desc(), EmrAppointment.token_number))).all()
    return [_appt_response(a, pn, dn) for a, pn, dn in rows]


@router.get("/appointments/{appointment_id}")
async def get_appointment(appointment_id: str, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "appointments:view", db)
    appt = await get_owned_or_404(
        db, EmrAppointment, appointment_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Appointment not found",
        extra_conditions=[EmrAppointment.deleted_at.is_(None)])
    return _appt_response(appt, *await _names(db, appt))


@router.put("/appointments/{appointment_id}")
async def reschedule_appointment(appointment_id: str, data: dict, request: Request,
                                 current_user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """Move a still-`booked` visit to another doctor/date/slot, or edit its reason."""
    await _require_emr_permission(current_user, "appointments:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    appt = await get_owned_or_404(
        db, EmrAppointment, appointment_id, pharmacy_id, not_found_detail="Appointment not found",
        extra_conditions=[EmrAppointment.deleted_at.is_(None)])
    if appt.status != APPT_BOOKED:
        raise HTTPException(
            status_code=409, detail=f"Only a booked appointment can be changed (this one is {appt.status})")
    old = _appt_response(appt)
    try:
        day = date.fromisoformat(data["appointment_date"]) if "appointment_date" in data else appt.appointment_date
        start = time.fromisoformat(data["start_time"]) if "start_time" in data else appt.start_time
        doctor_id = uuid.UUID(data["doctor_user_id"]) if "doctor_user_id" in data else appt.doctor_user_id
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid date, time or doctor id")
    if day < date.today():
        raise HTTPException(status_code=422, detail="Cannot move an appointment into the past")
    await _check_patient_doctor(db, pharmacy_id, appt.patient_id, doctor_id)
    moved = (day, start, doctor_id) != (appt.appointment_date, appt.start_time, appt.doctor_user_id)
    if moved:
        if start is None:
            raise HTTPException(status_code=422, detail="Pick a time slot to reschedule")
        appt.end_time = await _resolve_slot(db, pharmacy_id, doctor_id, day, start, appt.id)
        appt.token_number = await _next_token(db, pharmacy_id, doctor_id, day)
        appt.appointment_date, appt.start_time, appt.doctor_user_id = day, start, doctor_id
        appt.appointment_type = APPT_TYPE_SCHEDULED
    if "reason" in data:
        appt.reason = data["reason"]
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Someone just booked that slot — please pick another")
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update", "emr_appointment", appt.id,
        _appt_response(appt), db, old_values=old, ip_address=_client_ip(request))
    return _appt_response(appt, *await _names(db, appt))


@router.post("/appointments/{appointment_id}/status")
async def change_appointment_status(appointment_id: str, data: StatusChange, request: Request,
                                    current_user: User = Depends(get_current_user),
                                    db: AsyncSession = Depends(get_db)):
    """Queue moves: check in, start consult, complete, cancel (with reason), no-show."""
    cancelling = data.status == APPT_CANCELLED
    await _require_emr_permission(
        current_user, "appointments:cancel" if cancelling else "appointments:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    appt = await get_owned_or_404(
        db, EmrAppointment, appointment_id, pharmacy_id, not_found_detail="Appointment not found",
        extra_conditions=[EmrAppointment.deleted_at.is_(None)])
    if data.status not in APPOINTMENT_TRANSITIONS.get(appt.status, ()):
        raise HTTPException(
            status_code=409, detail=f"Cannot move an appointment from {appt.status} to {data.status}")
    if cancelling and not (data.cancel_reason and data.cancel_reason.strip()):
        raise HTTPException(status_code=422, detail="A reason is required to cancel an appointment")
    old = {"status": appt.status}
    now = datetime.now(timezone.utc)
    if data.status == APPT_CHECKED_IN:
        appt.checked_in_at = now
    elif data.status == APPT_IN_CONSULT:
        appt.started_at = now
    elif data.status == APPT_COMPLETED:
        appt.completed_at = now
    elif cancelling:
        appt.cancel_reason = data.cancel_reason.strip()
    appt.status = data.status
    await db.flush()
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "status_change", "emr_appointment", appt.id,
        {"status": appt.status, "cancel_reason": appt.cancel_reason}, db, old_values=old,
        ip_address=_client_ip(request))
    return _appt_response(appt, *await _names(db, appt))
