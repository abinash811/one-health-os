"""EMR clinic settings + this clinic's doctors and their fees (docs/28_EMR_SCOPE.md → Settings).
Any clinic user can READ settings (the patient form and printouts need them);
only roles with `emr_settings:edit` can change them. Doctor PROFILES (name, registration…) belong to the
hospital and are edited under Settings → Organisation → Doctors (docs/31_CORE_DOCTOR_SCOPE.md); here a
clinic only sets its own consultation fee for each doctor mapped to it."""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.clinics import Clinic
from models.practitioners import PractitionerClinic
from modules.emr.common import _client_ip, _record_audit, _require_emr_permission
from modules.emr.constants import FIELD_STATES, MAX_SLOT_MINUTES, MIN_SLOT_MINUTES, PATIENT_FORM_DEFAULTS
from modules.emr.doctors import clinic_doctors, get_clinic_doctor
from modules.emr.models import EmrSettings
from modules.emr.settings_service import effective_patient_form, get_or_create_settings
from modules.patient_billing.constants import MAX_AMOUNT_PAISE
from routers.auth_helpers import User, get_current_user
from services.clinics import active_clinic_id

router = APIRouter(prefix="/api/emr", tags=["emr-settings"])

_PREFIX = re.compile(r"^[A-Za-z0-9-]{1,10}$")


class SettingsUpdate(BaseModel):
    clinic_name: Optional[str] = Field(None, max_length=200)
    clinic_address: Optional[str] = None
    clinic_phone: Optional[str] = Field(None, max_length=20)
    clinic_email: Optional[str] = Field(None, max_length=200)
    registration_no: Optional[str] = Field(None, max_length=100)
    rx_footer: Optional[str] = None
    rx_prefix: Optional[str] = None
    uhid_prefix: Optional[str] = None
    uhid_digits: Optional[int] = None
    default_slot_minutes: Optional[int] = None
    patient_form: Optional[dict] = None


class ClinicDoctorFee(BaseModel):
    consultation_fee_paise: Optional[int] = Field(None, ge=0, le=MAX_AMOUNT_PAISE)


async def _settings_response(db, s: EmrSettings) -> dict:
    ph = (await db.execute(  # tenant-safe: settings row is clinic-scoped
        select(Clinic).where(Clinic.id == s.clinic_id))).scalar_one()
    return {
        "clinic_name": s.clinic_name, "clinic_address": s.clinic_address, "clinic_phone": s.clinic_phone,
        "clinic_email": s.clinic_email, "registration_no": s.registration_no, "rx_footer": s.rx_footer,
        "rx_prefix": s.rx_prefix, "uhid_prefix": s.uhid_prefix, "uhid_digits": s.uhid_digits,
        "uhid_next": s.uhid_next, "default_slot_minutes": s.default_slot_minutes,
        "patient_form": effective_patient_form(s),
        # What printouts show when the clinic fields above are left blank.
        "fallback": {"clinic_name": ph.name, "clinic_address": ph.address, "clinic_phone": ph.phone},
    }


@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:view", db)
    s = await get_or_create_settings(db, active_clinic_id(current_user))
    return await _settings_response(db, s)


@router.put("/settings")
async def update_settings(data: SettingsUpdate, request: Request,
                          current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "emr_settings:edit", db)
    clinic_id = active_clinic_id(current_user)
    s = await get_or_create_settings(db, clinic_id)
    changes = data.model_dump(exclude_unset=True)
    for key in ("rx_prefix", "uhid_prefix"):
        if key in changes and not _PREFIX.match(changes[key] or ""):
            raise HTTPException(status_code=422, detail=f"{key} must be 1-10 letters, numbers or dashes")
    if "uhid_digits" in changes and not 3 <= changes["uhid_digits"] <= 10:
        raise HTTPException(status_code=422, detail="uhid_digits must be between 3 and 10")
    slot = changes.get("default_slot_minutes")
    if slot is not None and not MIN_SLOT_MINUTES <= slot <= MAX_SLOT_MINUTES:
        raise HTTPException(
            status_code=422,
            detail=f"default_slot_minutes must be between {MIN_SLOT_MINUTES} and {MAX_SLOT_MINUTES}")
    if "patient_form" in changes:
        form = changes["patient_form"] or {}
        for field, state in form.items():
            if field not in PATIENT_FORM_DEFAULTS:
                raise HTTPException(status_code=422, detail=f"'{field}' cannot be configured on the patient form")
            if state not in FIELD_STATES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Field state for '{field}' must be one of {', '.join(FIELD_STATES)}")
        changes["patient_form"] = {**effective_patient_form(s), **form}
    old = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v.strip() if isinstance(v, str) and k not in ("clinic_address", "rx_footer") else v)
    await db.flush()
    await db.refresh(s)
    await _record_audit(clinic_id, uuid.UUID(current_user.id), "update", "emr_settings", s.id,
                        changes, db, old_values=old, ip_address=_client_ip(request))
    return await _settings_response(db, s)


def _clinic_doctor_dict(p, fee: Optional[int]) -> dict:
    return {"id": str(p.id), "name": p.name, "specialty": p.specialty, "qualification": p.qualification,
            "registration_no": p.registration_no, "consultation_fee_paise": fee}


@router.get("/clinic-doctors")
async def list_clinic_doctors(current_user: User = Depends(get_current_user),
                              db: AsyncSession = DbSession):
    """The doctors mapped to this clinic, with this clinic's consultation fee for each."""
    await _require_emr_permission(current_user, "patients:view", db)
    clinic_id = active_clinic_id(current_user)
    return [_clinic_doctor_dict(p, fee) for p, fee in await clinic_doctors(db, clinic_id)]


@router.put("/clinic-doctors/{practitioner_id}")
async def update_clinic_doctor_fee(practitioner_id: uuid.UUID, data: ClinicDoctorFee, request: Request,
                                   current_user: User = Depends(get_current_user),
                                   db: AsyncSession = DbSession):
    """Set THIS clinic's consultation fee for a doctor mapped here (blank / 0 = no fee at check-in)."""
    await _require_emr_permission(current_user, "emr_settings:edit", db)
    clinic_id = active_clinic_id(current_user)
    doctor = await get_clinic_doctor(db, clinic_id, practitioner_id)
    link = (await db.execute(select(PractitionerClinic).where(
        PractitionerClinic.practitioner_id == doctor.id, PractitionerClinic.clinic_id == clinic_id,
        PractitionerClinic.deleted_at.is_(None)))).scalar_one()
    old = {"consultation_fee_paise": link.consultation_fee_paise}
    link.consultation_fee_paise = data.consultation_fee_paise
    await db.flush()
    await _record_audit(clinic_id, uuid.UUID(current_user.id), "update", "practitioner_clinic", link.id,
                        {"consultation_fee_paise": link.consultation_fee_paise, "practitioner_id": str(doctor.id)},
                        db, old_values=old, ip_address=_client_ip(request))
    return _clinic_doctor_dict(doctor, link.consultation_fee_paise)
