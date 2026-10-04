"""Doctors at a clinic — Settings → Organisation → Clinics → "Doctors at this clinic" (docs/32 P2c).

The clinic-side view of the same mapping the Doctors screen edits from the doctor's side
(`practitioner_clinics`): tick a doctor to practise here, with this clinic's fee; untick to remove. Nothing
is deleted — an unticked doctor is soft-unmapped and revived if ticked again."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.practitioners import Practitioner, PractitionerClinic
from models.users import AuditLog
from routers.auth_helpers import User, get_current_user, has_permission
from services.clinics import get_clinic_or_404
from services.practitioners import get_visible_or_404, practitioner_scope, visible_clause

router = APIRouter(prefix="/api", tags=["clinic-doctors"])

MAX_FEE_PAISE = 10_000_000


async def _require_doctors_permission(current_user: User, permission: str, db: AsyncSession) -> None:
    if not await has_permission(current_user, permission, db):
        raise HTTPException(status_code=403, detail=f"Your role does not have the '{permission}' permission")


async def _record_audit(current_user: User, request: Request, action: str, link_id: uuid.UUID, new: dict,
                        db: AsyncSession, old: dict | None = None) -> None:
    db.add(AuditLog(pharmacy_id=uuid.UUID(current_user.pharmacy_id), user_id=uuid.UUID(current_user.id),
                    action=action, entity_type="practitioner_clinic", entity_id=link_id, new_values=new,
                    old_values=old, ip_address=request.client.host if request.client else None))


class ClinicDoctorLink(BaseModel):
    consultation_fee_paise: Optional[int] = Field(default=None, ge=0, le=MAX_FEE_PAISE)
    is_active: bool = True


async def _scoped_clinic(db: AsyncSession, clinic_id: str, current_user: User):
    clinic = await get_clinic_or_404(db, clinic_id, uuid.UUID(current_user.pharmacy_id))
    scope = await practitioner_scope(db, current_user)
    if clinic.id not in scope.clinic_ids:
        raise HTTPException(status_code=403, detail="You don't have access to that clinic")
    return clinic, scope


@router.get("/clinics/{clinic_id}/doctors")
async def list_clinic_doctors(clinic_id: str, current_user: User = Depends(get_current_user),
                              db: AsyncSession = DbSession):
    """Every doctor the caller can see, with whether they practise at this clinic and their fee here."""
    await _require_doctors_permission(current_user, "clinics:view", db)
    await _require_doctors_permission(current_user, "doctors:view", db)
    clinic, scope = await _scoped_clinic(db, clinic_id, current_user)
    doctors = (await db.execute(select(Practitioner).where(
        *visible_clause(scope), Practitioner.is_active.is_(True)).order_by(Practitioner.name))).scalars().all()
    links = {x.practitioner_id: x for x in (await db.execute(select(PractitionerClinic).where(
        PractitionerClinic.clinic_id == clinic.id, PractitionerClinic.deleted_at.is_(None)))).scalars().all()}
    return [{
        "id": str(d.id), "name": d.name, "specialty": d.specialty, "registration_no": d.registration_no,
        "is_external": d.is_external, "mapped": d.id in links and links[d.id].is_active,
        "consultation_fee_paise": links[d.id].consultation_fee_paise if d.id in links else None,
    } for d in doctors]


@router.put("/clinics/{clinic_id}/doctors/{practitioner_id}")
async def set_clinic_doctor(clinic_id: str, practitioner_id: str, body: ClinicDoctorLink, request: Request,
                            current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Make a doctor practise at this clinic (or change their fee here)."""
    await _require_doctors_permission(current_user, "doctors:edit", db)
    clinic, scope = await _scoped_clinic(db, clinic_id, current_user)
    doctor = await get_visible_or_404(db, practitioner_id, scope)
    link = (await db.execute(select(PractitionerClinic).where(
        PractitionerClinic.practitioner_id == doctor.id, PractitionerClinic.clinic_id == clinic.id))
    ).scalar_one_or_none()
    old = None
    if link is None:
        link = PractitionerClinic(practitioner_id=doctor.id, clinic_id=clinic.id)
        db.add(link)
    else:
        old = {"consultation_fee_paise": link.consultation_fee_paise, "is_active": link.is_active,
               "mapped": link.deleted_at is None}
    link.deleted_at = None
    link.consultation_fee_paise = body.consultation_fee_paise
    link.is_active = body.is_active
    await db.flush()
    await _record_audit(
        current_user, request, "update" if old else "create", link.id,
        {"doctor": doctor.name, "clinic": clinic.name, "consultation_fee_paise": link.consultation_fee_paise,
         "is_active": link.is_active}, db, old)
    await db.flush()
    return {"id": str(doctor.id), "mapped": True, "consultation_fee_paise": link.consultation_fee_paise}


@router.delete("/clinics/{clinic_id}/doctors/{practitioner_id}")
async def remove_clinic_doctor(clinic_id: str, practitioner_id: str, request: Request,
                               current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Stop a doctor practising here. Soft: existing appointments and prescriptions keep their history."""
    await _require_doctors_permission(current_user, "doctors:edit", db)
    clinic, scope = await _scoped_clinic(db, clinic_id, current_user)
    doctor = await get_visible_or_404(db, practitioner_id, scope)
    link = (await db.execute(select(PractitionerClinic).where(
        PractitionerClinic.practitioner_id == doctor.id, PractitionerClinic.clinic_id == clinic.id,
        PractitionerClinic.deleted_at.is_(None)))).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="That doctor is not mapped to this clinic")
    link.deleted_at, link.is_active = datetime.now(timezone.utc), False
    await db.flush()
    await _record_audit(current_user, request, "delete", link.id,
                        {"doctor": doctor.name, "clinic": clinic.name}, db, {"mapped": True})
    await db.flush()
    return {"message": "Doctor removed from this clinic"}
