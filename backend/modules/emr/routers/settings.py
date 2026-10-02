"""EMR clinic settings + doctor profiles (docs/28_EMR_SCOPE.md → Settings).
Any clinic user can READ settings (the patient form and printouts need them);
only roles with `emr_settings:edit` can change them."""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from deps import DbSession
from models.pharmacy import Pharmacy
from models.users import User as UserORM
from modules.emr.common import _client_ip, _record_audit, _require_emr_permission
from modules.emr.constants import (
    FIELD_STATES, MAX_SLOT_MINUTES, MIN_SLOT_MINUTES, PATIENT_FORM_DEFAULTS, ROLE_DOCTOR)
from modules.emr.models import EmrDoctorProfile, EmrSettings
from modules.emr.settings_service import effective_patient_form, get_or_create_settings
from modules.patient_billing.constants import MAX_AMOUNT_PAISE
from routers.auth_helpers import User, get_current_user, get_owned_or_404

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


class DoctorProfileUpdate(BaseModel):
    consultation_fee_paise: Optional[int] = Field(None, ge=0, le=MAX_AMOUNT_PAISE)
    specialty: Optional[str] = Field(None, max_length=100)
    qualification: Optional[str] = Field(None, max_length=200)
    registration_no: Optional[str] = Field(None, max_length=100)


async def _settings_response(db, s: EmrSettings) -> dict:
    ph = (await db.execute(select(Pharmacy).where(Pharmacy.id == s.pharmacy_id))).scalar_one()
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
    s = await get_or_create_settings(db, uuid.UUID(current_user.pharmacy_id))
    return await _settings_response(db, s)


@router.put("/settings")
async def update_settings(data: SettingsUpdate, request: Request,
                          current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "emr_settings:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    s = await get_or_create_settings(db, pharmacy_id)
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
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "update", "emr_settings", s.id,
                        changes, db, old_values=old, ip_address=_client_ip(request))
    return await _settings_response(db, s)


async def _profile(db, pharmacy_id, user_id) -> Optional[EmrDoctorProfile]:
    return (await db.execute(select(EmrDoctorProfile).where(
        EmrDoctorProfile.pharmacy_id == pharmacy_id, EmrDoctorProfile.user_id == user_id))).scalar_one_or_none()


def _profile_dict(u: UserORM, p: Optional[EmrDoctorProfile]) -> dict:
    return {"user_id": str(u.id), "name": u.name,
            "specialty": p.specialty if p else None, "qualification": p.qualification if p else None,
            "registration_no": p.registration_no if p else None,
            "consultation_fee_paise": p.consultation_fee_paise if p else None}


@router.get("/doctor-profiles")
async def list_doctor_profiles(current_user: User = Depends(get_current_user),
                               db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "patients:view", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    users = (await db.execute(
        select(UserORM).options(joinedload(UserORM.role)).where(
            UserORM.pharmacy_id == pharmacy_id, UserORM.is_active.is_(True)).order_by(UserORM.name))).scalars().all()
    profiles = {p.user_id: p for p in (await db.execute(select(EmrDoctorProfile).where(
        EmrDoctorProfile.pharmacy_id == pharmacy_id))).scalars().all()}
    return [_profile_dict(u, profiles.get(u.id)) for u in users if u.role.name == ROLE_DOCTOR or u.id in profiles]


@router.put("/doctor-profiles/{user_id}")
async def update_doctor_profile(user_id: uuid.UUID, data: DoctorProfileUpdate, request: Request,
                                current_user: User = Depends(get_current_user),
                                db: AsyncSession = DbSession):
    await _require_emr_permission(current_user, "emr_settings:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    user = await get_owned_or_404(db, UserORM, user_id, pharmacy_id, not_found_detail="Doctor not found",
                                  extra_conditions=[UserORM.is_active.is_(True)])
    profile = await _profile(db, pharmacy_id, user.id)
    old = {}
    if profile is None:
        profile = EmrDoctorProfile(pharmacy_id=pharmacy_id, user_id=user.id)
        db.add(profile)
    else:
        old = {"specialty": profile.specialty, "qualification": profile.qualification,
               "registration_no": profile.registration_no,
               "consultation_fee_paise": profile.consultation_fee_paise}
    changes = {k: (v.strip() or None if isinstance(v, str) else v)
               for k, v in data.model_dump(exclude_unset=True).items()}
    for k, v in changes.items():
        setattr(profile, k, v)
    await db.flush()
    await db.refresh(profile)
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "update", "emr_doctor_profile", profile.id,
                        changes, db, old_values=old or None, ip_address=_client_ip(request))
    return _profile_dict(user, profile)
