"""EMR appointments + today's queue (docs/28_EMR_SCOPE.md).
Scheduled visits must land on a doctor's working-hours slot; walk-ins just
take the next token for today."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.users import User as UserORM
from modules.emr.billing_hooks import fee_for_appointments, post_consultation_fee, withdraw_consultation_fee
from modules.emr.common import _client_ip, _record_audit, _require_emr_permission
from modules.emr.constants import (
    APPOINTMENT_TRANSITIONS, APPT_BOOKED, APPT_CANCELLED, APPT_CHECKED_IN, APPT_COMPLETED,
    APPT_IN_CONSULT, APPT_NO_SHOW, APPT_TYPE_SCHEDULED, APPT_TYPE_WALK_IN)
from modules.emr.models import EmrAppointment, EmrPatient
from modules.emr.slots import _booked_starts, _check_patient_doctor, _next_token, _resolve_slot, _slot_grid
from routers.auth_helpers import User, get_current_user, get_owned_or_404

router = APIRouter(prefix="/api/emr", tags=["emr-appointments"])


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    doctor_user_id: uuid.UUID
    appointment_date: date
    start_time: Optional[time] = None   # omitted = walk-in
    reason: Optional[str] = None


class StatusChange(BaseModel):
    status: str
    cancel_reason: Optional[str] = None


def _appt_response(a: EmrAppointment, patient_name=None, doctor_name=None, fee=None) -> dict:
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
        "fee": fee,
    }


async def _names(db, a: EmrAppointment):
    """Patient and doctor display names, both re-scoped to the appointment's own pharmacy."""
    p = (await db.execute(select(EmrPatient.name).where(
        EmrPatient.id == a.patient_id, EmrPatient.pharmacy_id == a.pharmacy_id))).scalar()
    d = (await db.execute(select(UserORM.name).where(
        UserORM.id == a.doctor_user_id, UserORM.pharmacy_id == a.pharmacy_id))).scalar()
    return p, d


@router.get("/slots")
async def available_slots(doctor_user_id: uuid.UUID, on_date: date = Query(..., alias="date"),
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "appointments:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    grid = await _slot_grid(db, pharmacy_id, doctor_user_id, on_date)
    taken = await _booked_starts(db, pharmacy_id, doctor_user_id, on_date)
    return [{"start_time": s.strftime("%H:%M"), "end_time": e.strftime("%H:%M"),
             "available": s not in taken} for s, e in grid]


@router.post("/appointments")
async def create_appointment(data: AppointmentCreate, request: Request,
                             current_user: User = Depends(get_current_user),
                             db: AsyncSession = DbSession):
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
    on_date: Optional[date] = Query(None, alias="date"),
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    doctor_user_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None, status: Optional[str] = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    """The day view / live queue. Defaults to today; ordered by token. `date_from`+`date_to`
    (max 31 days, inclusive) return a whole range — the calendar's week view."""
    await _require_emr_permission(current_user, "appointments:view", db)
    if (date_from is None) != (date_to is None):
        raise HTTPException(status_code=422, detail="Send both date_from and date_to")
    if date_from and date_to and (date_to < date_from or (date_to - date_from).days > 30):
        raise HTTPException(status_code=422, detail="Date range must be 1 to 31 days, start before end")
    query = (
        select(EmrAppointment, EmrPatient.name, UserORM.name)
        .join(EmrPatient, EmrPatient.id == EmrAppointment.patient_id)
        .join(UserORM, UserORM.id == EmrAppointment.doctor_user_id)
        .where(EmrAppointment.pharmacy_id == uuid.UUID(current_user.pharmacy_id),
               EmrAppointment.deleted_at.is_(None)))
    if date_from and date_to:
        query = query.where(EmrAppointment.appointment_date.between(date_from, date_to))
    elif on_date:
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
    fees = await fee_for_appointments(db, uuid.UUID(current_user.pharmacy_id), [a for a, _, _ in rows])
    return [_appt_response(a, pn, dn, fees.get(a.id)) for a, pn, dn in rows]


@router.get("/appointments/{appointment_id}")
async def get_appointment(appointment_id: str, current_user: User = Depends(get_current_user),
                          db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "appointments:view", db)
    appt = await get_owned_or_404(
        db, EmrAppointment, appointment_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Appointment not found",
        extra_conditions=[EmrAppointment.deleted_at.is_(None)])
    return _appt_response(appt, *await _names(db, appt))


@router.put("/appointments/{appointment_id}")
async def reschedule_appointment(appointment_id: str, data: dict, request: Request,
                                 current_user: User = Depends(get_current_user),
                                 db: AsyncSession = DbSession):
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
                                    db: AsyncSession = DbSession):
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
    uid = uuid.UUID(current_user.id)
    if data.status == APPT_CHECKED_IN:       # the consultation fee lands on the patient's account
        await post_consultation_fee(db, appt, uid, _client_ip(request))
    elif data.status in (APPT_CANCELLED, APPT_NO_SHOW):
        await withdraw_consultation_fee(
            db, appt, uid, f"Appointment {data.status.replace('_', ' ')}", _client_ip(request))
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "status_change", "emr_appointment", appt.id,
        {"status": appt.status, "cancel_reason": appt.cancel_reason}, db, old_values=old,
        ip_address=_client_ip(request))
    return _appt_response(appt, *await _names(db, appt))
