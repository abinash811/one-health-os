"""EMR prescriptions — ONE record per visit holding the whole consultation
(vitals, complaints, diagnosis, advice, follow-up) plus its medicine lines.
Draft is freely editable; issuing locks it for printing (docs/28_EMR_SCOPE.md)."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.pharmacy import Pharmacy
from models.users import User as UserORM
from modules.emr.common import _client_ip, _record_audit, _require_emr_permission
from modules.emr.constants import (
    APPT_CANCELLED, APPT_COMPLETED, APPT_IN_CONSULT, RX_CANCELLED, RX_DRAFT, RX_ISSUED)
from modules.emr.models import (
    EmrAppointment, EmrDoctorProfile, EmrPatient, EmrPrescription, EmrPrescriptionItem)
from modules.emr.settings_service import get_or_create_settings
from routers.auth_helpers import User, get_current_user, get_owned_or_404

router = APIRouter(prefix="/api/emr", tags=["emr-prescriptions"])

VITAL_KEYS = ("bp_systolic", "bp_diastolic", "pulse", "temperature_c", "spo2", "weight_kg")


class RxCreate(BaseModel):
    appointment_id: uuid.UUID


class RxItemIn(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=300)
    dosage: Optional[str] = Field(None, max_length=100)
    frequency: Optional[str] = Field(None, max_length=100)
    duration_days: Optional[int] = Field(None, ge=1, le=3650)
    instructions: Optional[str] = Field(None, max_length=300)
    quantity: Optional[int] = Field(None, ge=1, le=100000)


class RxUpdate(BaseModel):
    vitals: Optional[dict] = None
    complaints: Optional[str] = None
    diagnosis: Optional[str] = None
    advice: Optional[str] = None
    follow_up_date: Optional[date] = None
    items: list[RxItemIn] = []


class RxCancel(BaseModel):
    reason: str = Field(min_length=1)


def _clean_vitals(v: Optional[dict]) -> Optional[dict]:
    if not v:
        return None
    out = {}
    for k in VITAL_KEYS:
        if v.get(k) in (None, ""):
            continue
        if not isinstance(v[k], (int, float)) or v[k] < 0:
            raise HTTPException(status_code=422, detail=f"Vital '{k}' must be a positive number")
        out[k] = v[k]
    return out or None


async def _next_rx_number(db, pharmacy_id) -> str:
    """Next number = highest trailing number ever issued + 1, formatted with the clinic's
    current prefix — changing the prefix later never reuses or restarts numbers."""
    rows = (await db.execute(select(EmrPrescription.rx_number).where(
        EmrPrescription.pharmacy_id == pharmacy_id))).scalars().all()
    top = max((int(m.group()) for r in rows if (m := re.search(r"\d+$", r))), default=0)
    prefix = (await get_or_create_settings(db, pharmacy_id)).rx_prefix
    return f"{prefix}{top + 1:06d}"


async def _items(db, rx_id) -> list[EmrPrescriptionItem]:
    return list((await db.execute(select(EmrPrescriptionItem).where(
        EmrPrescriptionItem.prescription_id == rx_id).order_by(EmrPrescriptionItem.sort_order))).scalars())


async def _rx_response(db, rx: EmrPrescription, full: bool = True) -> dict:
    p = (await db.execute(select(EmrPatient).where(
        EmrPatient.id == rx.patient_id, EmrPatient.pharmacy_id == rx.pharmacy_id))).scalar_one_or_none()
    doc = (await db.execute(select(UserORM.name).where(
        UserORM.id == rx.doctor_user_id, UserORM.pharmacy_id == rx.pharmacy_id))).scalar()
    out = {
        "id": str(rx.id), "rx_number": rx.rx_number, "status": rx.status,
        "appointment_id": str(rx.appointment_id), "patient_id": str(rx.patient_id),
        "patient_name": p.name if p else None, "doctor_user_id": str(rx.doctor_user_id),
        "doctor_name": doc, "vitals": rx.vitals or {}, "complaints": rx.complaints,
        "diagnosis": rx.diagnosis, "advice": rx.advice,
        "follow_up_date": rx.follow_up_date.isoformat() if rx.follow_up_date else None,
        "issued_at": rx.issued_at.isoformat() if rx.issued_at else None,
        "cancel_reason": rx.cancel_reason, "created_at": rx.created_at.isoformat(),
    }
    if full:
        ph = (await db.execute(select(Pharmacy).where(Pharmacy.id == rx.pharmacy_id))).scalar_one()
        cfg = await get_or_create_settings(db, rx.pharmacy_id)
        prof = (await db.execute(select(EmrDoctorProfile).where(
            EmrDoctorProfile.pharmacy_id == rx.pharmacy_id,
            EmrDoctorProfile.user_id == rx.doctor_user_id))).scalar_one_or_none()
        out["items"] = [{
            "id": str(i.id), "medicine_name": i.medicine_name, "dosage": i.dosage,
            "frequency": i.frequency, "duration_days": i.duration_days,
            "instructions": i.instructions, "quantity": i.quantity} for i in await _items(db, rx.id)]
        out["patient"] = {
            "gender": p.gender, "phone": p.phone, "age": p.age, "allergies": p.allergies,
            "date_of_birth": p.date_of_birth.isoformat() if p and p.date_of_birth else None,
        } if p else None
        # Clinic identity from EMR settings; blank fields fall back to the pharmacy record.
        out["clinic"] = {
            "name": cfg.clinic_name or ph.name, "address": cfg.clinic_address or ph.address,
            "phone": cfg.clinic_phone or ph.phone, "email": cfg.clinic_email,
            "registration_no": cfg.registration_no, "footer": cfg.rx_footer}
        out["doctor"] = {
            "specialty": prof.specialty if prof else None, "qualification": prof.qualification if prof else None,
            "registration_no": prof.registration_no if prof else None}
        out["patient_uhid"] = p.uhid if p else None
    return out


async def _get_rx(db, rx_id, pharmacy_id) -> EmrPrescription:
    return await get_owned_or_404(
        db, EmrPrescription, rx_id, pharmacy_id, not_found_detail="Prescription not found",
        extra_conditions=[EmrPrescription.deleted_at.is_(None)])


@router.post("/prescriptions")
async def start_prescription(data: RxCreate, request: Request,
                             current_user: User = Depends(get_current_user),
                             db: AsyncSession = DbSession):
    """Starts the visit's prescription; if a live one already exists, returns it (so
    'Open Rx' is idempotent)."""
    await _require_emr_permission(current_user, "prescriptions:create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    appt = await get_owned_or_404(
        db, EmrAppointment, data.appointment_id, pharmacy_id, not_found_detail="Appointment not found",
        extra_conditions=[EmrAppointment.deleted_at.is_(None)])
    if appt.status == APPT_CANCELLED:
        raise HTTPException(status_code=409, detail="Cannot prescribe on a cancelled appointment")
    live = (await db.execute(select(EmrPrescription).where(
        EmrPrescription.pharmacy_id == pharmacy_id, EmrPrescription.appointment_id == appt.id,
        EmrPrescription.status != RX_CANCELLED, EmrPrescription.deleted_at.is_(None)))).scalar_one_or_none()
    if live:
        return await _rx_response(db, live)
    uid = uuid.UUID(current_user.id)
    # Two simultaneous opens (double-click, dev double-render) race on the same visit:
    # each attempt runs in a savepoint; the loser re-reads the winner's Rx instead of failing.
    rx = None
    for _ in range(3):
        candidate = EmrPrescription(
            pharmacy_id=pharmacy_id, appointment_id=appt.id, patient_id=appt.patient_id,
            doctor_user_id=appt.doctor_user_id, rx_number=await _next_rx_number(db, pharmacy_id),
            status=RX_DRAFT, created_by=uid)
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            rx = candidate
            break
        except IntegrityError:
            live = (await db.execute(select(EmrPrescription).where(
                EmrPrescription.pharmacy_id == pharmacy_id, EmrPrescription.appointment_id == appt.id,
                EmrPrescription.status != RX_CANCELLED, EmrPrescription.deleted_at.is_(None)))).scalar_one_or_none()
            if live:
                return await _rx_response(db, live)
    if rx is None:
        raise HTTPException(status_code=409, detail="Could not create the prescription — please retry")
    await db.refresh(rx)
    await _record_audit(pharmacy_id, uid, "create", "emr_prescription", rx.id,
                        {"rx_number": rx.rx_number, "appointment_id": str(appt.id)}, db,
                        ip_address=_client_ip(request))
    return await _rx_response(db, rx)


@router.get("/appointments/{appointment_id}/prescription")
async def appointment_prescription(appointment_id: uuid.UUID, current_user: User = Depends(get_current_user),
                                   db: AsyncSession = DbSession):
    """The visit's live (non-cancelled) prescription, read-only — so anyone who may VIEW prescriptions (e.g.
    the front desk) can open it without needing the permission to start one. 404 when there is none yet."""
    await _require_emr_permission(current_user, "prescriptions:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    live = (await db.execute(select(EmrPrescription).where(
        EmrPrescription.pharmacy_id == pharmacy_id, EmrPrescription.appointment_id == appointment_id,
        EmrPrescription.status != RX_CANCELLED, EmrPrescription.deleted_at.is_(None)))).scalar_one_or_none()
    if not live:
        raise HTTPException(status_code=404, detail="No prescription for this visit yet")
    return await _rx_response(db, live)


@router.get("/prescriptions/suggestions")
async def medicine_suggestions(q: str = Query("", max_length=100), limit: int = Query(200, le=500),
                               current_user: User = Depends(get_current_user),
                               db: AsyncSession = DbSession):
    """Medicines this clinic has prescribed before, most-used first — the 'own history' autocomplete."""
    await _require_emr_permission(current_user, "prescriptions:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    stmt = select(EmrPrescriptionItem.medicine_name, func.count().label("n")).where(
        EmrPrescriptionItem.pharmacy_id == pharmacy_id)
    if q.strip():
        stmt = stmt.where(EmrPrescriptionItem.medicine_name.ilike(f"%{q.strip()}%"))
    rows = (await db.execute(stmt.group_by(EmrPrescriptionItem.medicine_name)
                             .order_by(func.count().desc()).limit(limit))).all()
    return [r[0] for r in rows]


@router.get("/patients/{patient_id}/prescriptions")
async def patient_prescriptions(patient_id: uuid.UUID, current_user: User = Depends(get_current_user),
                                db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "prescriptions:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    await get_owned_or_404(db, EmrPatient, patient_id, pharmacy_id, not_found_detail="Patient not found",
                           extra_conditions=[EmrPatient.deleted_at.is_(None)])
    rows = (await db.execute(select(EmrPrescription).where(
        EmrPrescription.pharmacy_id == pharmacy_id, EmrPrescription.patient_id == patient_id,
        EmrPrescription.deleted_at.is_(None)).order_by(EmrPrescription.created_at.desc()))).scalars().all()
    return [await _rx_response(db, r) for r in rows]


@router.get("/prescriptions/{rx_id}")
async def get_prescription(rx_id: uuid.UUID, current_user: User = Depends(get_current_user),
                           db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "prescriptions:view", db)
    rx = await _get_rx(db, rx_id, uuid.UUID(current_user.pharmacy_id))
    return await _rx_response(db, rx)


@router.put("/prescriptions/{rx_id}")
async def update_prescription(rx_id: uuid.UUID, data: RxUpdate, request: Request,
                              current_user: User = Depends(get_current_user),
                              db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "prescriptions:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    rx = await _get_rx(db, rx_id, pharmacy_id)
    if rx.status != RX_DRAFT:
        raise HTTPException(status_code=409, detail="Only a draft prescription can be edited")
    rx.vitals = _clean_vitals(data.vitals)
    rx.complaints, rx.diagnosis, rx.advice = data.complaints, data.diagnosis, data.advice
    rx.follow_up_date = data.follow_up_date
    for old in await _items(db, rx.id):
        await db.delete(old)
    await db.flush()
    for n, it in enumerate(data.items):
        db.add(EmrPrescriptionItem(
            pharmacy_id=pharmacy_id, prescription_id=rx.id, sort_order=n,
            **{**it.model_dump(), "medicine_name": it.medicine_name.strip()}))
    await db.flush()
    await db.refresh(rx)
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "update", "emr_prescription", rx.id,
                        {"items": len(data.items), "diagnosis": data.diagnosis}, db,
                        ip_address=_client_ip(request))
    return await _rx_response(db, rx)


@router.post("/prescriptions/{rx_id}/issue")
async def issue_prescription(rx_id: uuid.UUID, request: Request,
                             current_user: User = Depends(get_current_user),
                             db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "prescriptions:issue", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    rx = await _get_rx(db, rx_id, pharmacy_id)
    if rx.status != RX_DRAFT:
        raise HTTPException(status_code=409, detail=f"A {rx.status} prescription cannot be issued")
    if not await _items(db, rx.id):
        raise HTTPException(status_code=422, detail="Add at least one medicine before issuing")
    rx.status, rx.issued_at = RX_ISSUED, datetime.now(timezone.utc)
    # Issuing the Rx ends the consult — the doctor shouldn't need a second click to close the visit.
    appt = await get_owned_or_404(db, EmrAppointment, rx.appointment_id, pharmacy_id,
                                  not_found_detail="Appointment not found")
    if appt.status == APPT_IN_CONSULT:
        appt.status, appt.completed_at = APPT_COMPLETED, rx.issued_at
    await db.flush()
    await db.refresh(rx)
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "issue", "emr_prescription", rx.id,
                        {"rx_number": rx.rx_number}, db, ip_address=_client_ip(request))
    return await _rx_response(db, rx)


@router.post("/prescriptions/{rx_id}/cancel")
async def cancel_prescription(rx_id: uuid.UUID, data: RxCancel, request: Request,
                              current_user: User = Depends(get_current_user),
                              db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "prescriptions:cancel", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    rx = await _get_rx(db, rx_id, pharmacy_id)
    if rx.status == RX_CANCELLED:
        raise HTTPException(status_code=409, detail="Prescription is already cancelled")
    rx.status, rx.cancel_reason = RX_CANCELLED, data.reason.strip()
    await db.flush()
    await db.refresh(rx)
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "cancel", "emr_prescription", rx.id,
                        {"reason": rx.cancel_reason}, db, ip_address=_client_ip(request))
    return await _rx_response(db, rx)
