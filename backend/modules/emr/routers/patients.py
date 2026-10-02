"""EMR patients — the clinic's own patient records (docs/28_EMR_SCOPE.md).
Independent of the pharmacy `customers` table by design."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from modules.emr.common import (
    _client_ip, _record_audit, _require_emr_permission, _validate_phone_length)
from modules.emr.constants import FIELD_REQUIRED
from modules.emr.models import EmrPatient
from modules.emr.settings_service import effective_patient_form, get_or_create_settings, next_uhid
from routers.auth_helpers import User, get_current_user, get_owned_or_404, paginate_response

router = APIRouter(prefix="/api/emr", tags=["emr-patients"])

PATIENT_EDITABLE = {
    "name", "phone", "alternate_phone", "email", "date_of_birth", "age", "gender",
    "blood_group", "address", "city", "allergies", "notes",
}


class PatientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None

    _v_phone = field_validator("phone", "alternate_phone")(_validate_phone_length)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Patient name is required")
        return v.strip()


FIELD_LABELS = {
    "phone": "Mobile", "alternate_phone": "Alternate mobile", "age": "Age", "date_of_birth": "Date of birth",
    "gender": "Gender", "blood_group": "Blood group", "city": "City", "allergies": "Allergies", "notes": "Notes",
}


async def _enforce_required(db, pharmacy_id, values: dict, only_keys=None) -> None:
    """The clinic's patient-form settings decide which fields must be filled. On create every
    required field is checked; on edit only the fields actually being sent are."""
    form = effective_patient_form(await get_or_create_settings(db, pharmacy_id))
    missing = [FIELD_LABELS[f] for f, state in form.items()
               if state == FIELD_REQUIRED and (only_keys is None or f in only_keys)
               and values.get(f) in (None, "")]
    if missing:
        verb = "is" if len(missing) == 1 else "are"
        raise HTTPException(status_code=422, detail=f"{', '.join(missing)} {verb} required")


def _patient_response(p: EmrPatient) -> dict:
    return {
        "id": str(p.id), "uhid": p.uhid, "name": p.name, "phone": p.phone, "alternate_phone": p.alternate_phone,
        "email": p.email,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "age": p.age, "gender": p.gender, "blood_group": p.blood_group,
        "address": p.address, "city": p.city, "allergies": p.allergies, "notes": p.notes,
        "source": p.source, "customer_id": str(p.customer_id) if p.customer_id else None,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _audit_safe(data: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in data.items()}


@router.post("/patients")
async def create_patient(data: PatientCreate, request: Request,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    await _enforce_required(db, pharmacy_id, data.model_dump())
    patient = EmrPatient(pharmacy_id=pharmacy_id, uhid=await next_uhid(db, pharmacy_id), **data.model_dump())
    db.add(patient)
    await db.flush()
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "emr_patient", patient.id,
        _audit_safe(data.model_dump()), db, ip_address=_client_ip(request))
    return _patient_response(patient)


@router.get("/patients")
async def list_patients(page: int = 1, page_size: int = 50, search: Optional[str] = None,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    query = select(EmrPatient).where(
        EmrPatient.pharmacy_id == pharmacy_id, EmrPatient.deleted_at.is_(None))
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(
            EmrPatient.name.ilike(pattern), EmrPatient.phone.ilike(pattern), EmrPatient.uhid.ilike(pattern),
            EmrPatient.alternate_phone.ilike(pattern)))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    rows = (await db.execute(
        query.order_by(EmrPatient.name).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return paginate_response([_patient_response(p) for p in rows], page, page_size, total)


@router.get("/patients/{patient_id}")
async def get_patient(patient_id: str, current_user: User = Depends(get_current_user),
                      db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:view", db)
    patient = await get_owned_or_404(
        db, EmrPatient, patient_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Patient not found",
        extra_conditions=[EmrPatient.deleted_at.is_(None)])
    return _patient_response(patient)


@router.put("/patients/{patient_id}")
async def update_patient(patient_id: str, data: dict, request: Request,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    patient = await get_owned_or_404(
        db, EmrPatient, patient_id, pharmacy_id, not_found_detail="Patient not found",
        extra_conditions=[EmrPatient.deleted_at.is_(None)])
    sent = {k: v for k, v in data.items() if k in PATIENT_EDITABLE}
    await _enforce_required(db, pharmacy_id, sent, only_keys=set(sent))
    old_values: dict = {}
    new_values: dict = {}
    for key, value in data.items():
        if key not in PATIENT_EDITABLE:
            continue
        if key == "name" and not (isinstance(value, str) and value.strip()):
            raise HTTPException(status_code=422, detail="Patient name is required")
        if key in ("phone", "alternate_phone") and value is not None and len(value) > 10:
            raise HTTPException(status_code=422, detail="Phone number must be at most 10 characters")
        if key == "date_of_birth" and value is not None:
            try:
                value = date.fromisoformat(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="date_of_birth must be YYYY-MM-DD")
        old_values[key] = getattr(patient, key)
        setattr(patient, key, value)
        new_values[key] = value
    await db.flush()
    await db.refresh(patient)  # updated_at is set by the DB on UPDATE; reload before responding
    if new_values:
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "update", "emr_patient", patient.id,
            _audit_safe(new_values), db, old_values=_audit_safe(old_values),
            ip_address=_client_ip(request))
    return _patient_response(patient)


@router.delete("/patients/{patient_id}")
async def delete_patient(patient_id: str, request: Request,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:delete", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    patient = await get_owned_or_404(
        db, EmrPatient, patient_id, pharmacy_id, not_found_detail="Patient not found",
        extra_conditions=[EmrPatient.deleted_at.is_(None)])
    patient.deleted_at = datetime.now(timezone.utc)
    patient.is_active = False
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "delete", "emr_patient", patient.id,
        {"name": patient.name}, db, ip_address=_client_ip(request))
    return {"message": "Patient deleted"}
