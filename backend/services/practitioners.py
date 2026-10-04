"""Doctor records (docs/31_CORE_DOCTOR_SCOPE.md): who may see a doctor, and how one is shaped for the API.

Doctors belong to the workspace. An administrator sees all of them; everyone else sees doctors created at their
own place or mapped to a clinic they can actually open (their `user_clinic_access` rows)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.clinics import Clinic
from models.practitioners import Practitioner, PractitionerClinic
from models.users import User as UserORM, UserClinicAccess
from routers.auth_helpers import has_permission
from services.clinics import list_clinics
from services.workspace import caller_workspace


@dataclass
class Scope:
    """What the caller may see of the doctor list: their workspace, the clinics they can open, and whether they
    see everything (an administrator)."""
    chain_id: uuid.UUID
    anchor_pharmacy_id: uuid.UUID
    clinic_ids: list[uuid.UUID]
    see_all: bool


async def practitioner_scope(db: AsyncSession, current_user) -> Scope:
    chain_id = await caller_workspace(db, current_user)
    see_all = await has_permission(current_user, "*", db)
    if see_all:
        clinic_ids = [c.id for c in await list_clinics(db, uuid.UUID(current_user.pharmacy_id),
                                                       include_inactive=True)]
    else:
        clinic_ids = list((await db.execute(select(UserClinicAccess.clinic_id).where(
            UserClinicAccess.user_id == uuid.UUID(current_user.id)))).scalars().all())
    return Scope(chain_id, uuid.UUID(current_user.pharmacy_id), clinic_ids, see_all)


def visible_clause(scope: Scope):
    """SQL condition: in the caller's workspace, and (for non-administrators) created at the caller's place or
    mapped to a clinic the caller can open — and not deleted."""
    base = (Practitioner.deleted_at.is_(None), Practitioner.chain_id == scope.chain_id)
    if scope.see_all:
        return base
    mapped = select(PractitionerClinic.practitioner_id).where(
        PractitionerClinic.clinic_id.in_(scope.clinic_ids), PractitionerClinic.deleted_at.is_(None))
    return (*base, or_(Practitioner.pharmacy_id == scope.anchor_pharmacy_id, Practitioner.id.in_(mapped)))


async def get_visible_or_404(db: AsyncSession, practitioner_id, scope: Scope) -> Practitioner:
    try:
        pid = uuid.UUID(str(practitioner_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Doctor not found")
    found = (await db.execute(
        select(Practitioner).where(Practitioner.id == pid, *visible_clause(scope)))).scalar_one_or_none()
    if not found:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return found


async def clinics_for(db: AsyncSession, practitioner_ids: list[uuid.UUID], scope: Scope) -> dict:
    """{practitioner_id: [clinic rows the caller may see]} — mappings at clinics outside the caller's
    grants are never shown."""
    if not practitioner_ids:
        return {}
    rows = (await db.execute(
        select(PractitionerClinic, Clinic.name)
        .join(Clinic, Clinic.id == PractitionerClinic.clinic_id)  # tenant-safe: filtered to the scope below
        .where(PractitionerClinic.practitioner_id.in_(practitioner_ids),
               PractitionerClinic.clinic_id.in_(scope.clinic_ids),
               PractitionerClinic.deleted_at.is_(None))
        .order_by(Clinic.name))).all()
    out: dict = {}
    for link, clinic_name in rows:
        out.setdefault(link.practitioner_id, []).append({
            "clinic_id": str(link.clinic_id), "clinic_name": clinic_name,
            "consultation_fee_paise": link.consultation_fee_paise, "is_active": link.is_active})
    return out


async def login_for(db: AsyncSession, user_ids: list[uuid.UUID], chain_id: uuid.UUID) -> dict:
    """{user_id: (name, email)} for linked logins in the caller's workspace."""
    if not user_ids:
        return {}
    rows = (await db.execute(select(UserORM.id, UserORM.name, UserORM.email).where(
        UserORM.id.in_(user_ids), UserORM.chain_id == chain_id))).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def shape(p: Practitioner, clinics: list, login: Optional[tuple]) -> dict:
    return {
        "id": str(p.id), "name": p.name, "specialty": p.specialty, "qualification": p.qualification,
        "registration_no": p.registration_no, "phone": p.phone, "email": p.email,
        "is_external": p.is_external, "hospital": p.hospital, "notes": p.notes, "is_active": p.is_active,
        "chain_id": str(p.chain_id),
        "user_id": str(p.user_id) if p.user_id else None,
        "user_name": login[0] if login else None, "user_email": login[1] if login else None,
        "clinics": clinics,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def shape_many(db: AsyncSession, items: list[Practitioner], scope: Scope) -> list[dict]:
    clinic_map = await clinics_for(db, [p.id for p in items], scope)
    logins = await login_for(db, [p.user_id for p in items if p.user_id], scope.chain_id)
    return [shape(p, clinic_map.get(p.id, []), logins.get(p.user_id)) for p in items]
