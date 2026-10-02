"""EMR doctor working hours + the doctor list (docs/28_EMR_SCOPE.md).
A doctor is a login user; a user shows up in the doctor list if their role is
`doctor` or they already have a schedule block."""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from deps import get_db
from models.users import User as UserORM
from modules.emr.common import _client_ip, _record_audit, _require_emr_permission
from modules.emr.constants import MAX_SLOT_MINUTES, MIN_SLOT_MINUTES, ROLE_DOCTOR
from modules.emr.models import EmrDoctorSchedule
from routers.auth_helpers import User, get_current_user, get_owned_or_404

router = APIRouter(prefix="/api/emr", tags=["emr-schedules"])


class ScheduleCreate(BaseModel):
    doctor_user_id: uuid.UUID
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int = 15


def _schedule_response(s: EmrDoctorSchedule) -> dict:
    return {
        "id": str(s.id), "doctor_user_id": str(s.doctor_user_id), "weekday": s.weekday,
        "start_time": s.start_time.strftime("%H:%M"), "end_time": s.end_time.strftime("%H:%M"),
        "slot_minutes": s.slot_minutes, "is_active": s.is_active,
    }


def _validate_block(weekday: int, start: time, end: time, slot_minutes: int) -> None:
    if not 0 <= weekday <= 6:
        raise HTTPException(status_code=422, detail="weekday must be 0 (Monday) to 6 (Sunday)")
    if start >= end:
        raise HTTPException(status_code=422, detail="Start time must be before end time")
    if not MIN_SLOT_MINUTES <= slot_minutes <= MAX_SLOT_MINUTES:
        raise HTTPException(
            status_code=422,
            detail=f"slot_minutes must be between {MIN_SLOT_MINUTES} and {MAX_SLOT_MINUTES}")


async def _assert_active_staff(db: AsyncSession, pharmacy_id: uuid.UUID, user_id: uuid.UUID) -> UserORM:
    user = await get_owned_or_404(
        db, UserORM, user_id, pharmacy_id, not_found_detail="Doctor not found",
        extra_conditions=[UserORM.is_active.is_(True)])
    return user


async def _assert_no_overlap(db, pharmacy_id, doctor_user_id, weekday, start, end, ignore_id=None):
    rows = (await db.execute(select(EmrDoctorSchedule).where(
        EmrDoctorSchedule.pharmacy_id == pharmacy_id,
        EmrDoctorSchedule.doctor_user_id == doctor_user_id,
        EmrDoctorSchedule.weekday == weekday,
        EmrDoctorSchedule.deleted_at.is_(None)))).scalars().all()
    for r in rows:
        if r.id != ignore_id and start < r.end_time and r.start_time < end:
            raise HTTPException(
                status_code=409,
                detail=f"Overlaps an existing block {r.start_time:%H:%M}–{r.end_time:%H:%M} on that day")


@router.get("/doctors")
async def list_doctors(current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "appointments:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    scheduled_ids = set((await db.execute(
        select(EmrDoctorSchedule.doctor_user_id).where(
            EmrDoctorSchedule.pharmacy_id == pharmacy_id,
            EmrDoctorSchedule.deleted_at.is_(None)))).scalars().all())
    users = (await db.execute(
        select(UserORM).options(joinedload(UserORM.role)).where(
            UserORM.pharmacy_id == pharmacy_id, UserORM.is_active.is_(True))
        .order_by(UserORM.name))).scalars().all()
    return [{"id": str(u.id), "name": u.name, "role": u.role.name}
            for u in users if u.role.name == ROLE_DOCTOR or u.id in scheduled_ids]


@router.get("/schedules")
async def list_schedules(doctor_user_id: Optional[uuid.UUID] = None,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "schedules:view", db)
    query = select(EmrDoctorSchedule).where(
        EmrDoctorSchedule.pharmacy_id == uuid.UUID(current_user.pharmacy_id),
        EmrDoctorSchedule.deleted_at.is_(None))
    if doctor_user_id:
        query = query.where(EmrDoctorSchedule.doctor_user_id == doctor_user_id)
    rows = (await db.execute(query.order_by(
        EmrDoctorSchedule.weekday, EmrDoctorSchedule.start_time))).scalars().all()
    return [_schedule_response(s) for s in rows]


@router.post("/schedules")
async def create_schedule(data: ScheduleCreate, request: Request,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "schedules:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    _validate_block(data.weekday, data.start_time, data.end_time, data.slot_minutes)
    await _assert_active_staff(db, pharmacy_id, data.doctor_user_id)
    await _assert_no_overlap(
        db, pharmacy_id, data.doctor_user_id, data.weekday, data.start_time, data.end_time)
    block = EmrDoctorSchedule(pharmacy_id=pharmacy_id, **data.model_dump())
    db.add(block)
    await db.flush()
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "emr_schedule", block.id,
        _schedule_response(block), db, ip_address=_client_ip(request))
    return _schedule_response(block)


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, data: dict, request: Request,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "schedules:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    block = await get_owned_or_404(
        db, EmrDoctorSchedule, schedule_id, pharmacy_id, not_found_detail="Schedule not found",
        extra_conditions=[EmrDoctorSchedule.deleted_at.is_(None)])
    old = _schedule_response(block)
    try:
        start = time.fromisoformat(data["start_time"]) if "start_time" in data else block.start_time
        end = time.fromisoformat(data["end_time"]) if "end_time" in data else block.end_time
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Times must be HH:MM")
    slot = data.get("slot_minutes", block.slot_minutes)
    weekday = data.get("weekday", block.weekday)
    _validate_block(weekday, start, end, slot)
    await _assert_no_overlap(db, pharmacy_id, block.doctor_user_id, weekday, start, end, block.id)
    block.start_time, block.end_time, block.slot_minutes, block.weekday = start, end, slot, weekday
    if "is_active" in data:
        block.is_active = bool(data["is_active"])
    await db.flush()
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update", "emr_schedule", block.id,
        _schedule_response(block), db, old_values=old, ip_address=_client_ip(request))
    return _schedule_response(block)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, request: Request,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    await _require_emr_permission(current_user, "schedules:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    block = await get_owned_or_404(
        db, EmrDoctorSchedule, schedule_id, pharmacy_id, not_found_detail="Schedule not found",
        extra_conditions=[EmrDoctorSchedule.deleted_at.is_(None)])
    block.deleted_at = datetime.now(timezone.utc)
    block.is_active = False
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "delete", "emr_schedule", block.id,
        _schedule_response(block), db, ip_address=_client_ip(request))
    return {"message": "Schedule block removed"}
