"""Doctor records (docs/31_CORE_DOCTOR_SCOPE.md): who may see a doctor, and how one is shaped for the API.

Visibility is decided from the caller's REAL store grants (`resolve_chain_scope_pids` — the one sanctioned,
grant-checked helper), never from a raw chain_id filter: a doctor is visible when they were created at, or are
mapped to, a clinic the caller actually has access to."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pharmacy import Pharmacy
from models.practitioners import Practitioner, PractitionerClinic
from models.users import User as UserORM


def visible_clause(pids: list[uuid.UUID]):
    """SQL condition: created at, or mapped to, one of these clinics (and not deleted)."""
    mapped = select(PractitionerClinic.practitioner_id).where(
        PractitionerClinic.pharmacy_id.in_(pids), PractitionerClinic.deleted_at.is_(None))
    return (Practitioner.deleted_at.is_(None),
            or_(Practitioner.pharmacy_id.in_(pids), Practitioner.id.in_(mapped)))


async def get_visible_or_404(db: AsyncSession, practitioner_id, pids: list[uuid.UUID]) -> Practitioner:
    try:
        pid = uuid.UUID(str(practitioner_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Doctor not found")
    found = (await db.execute(
        select(Practitioner).where(Practitioner.id == pid, *visible_clause(pids)))).scalar_one_or_none()
    if not found:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return found


async def clinics_for(db: AsyncSession, practitioner_ids: list[uuid.UUID], pids: list[uuid.UUID]) -> dict:
    """{practitioner_id: [clinic rows the caller may see]} — mappings at clinics outside the caller's
    grants are never shown."""
    if not practitioner_ids:
        return {}
    rows = (await db.execute(
        select(PractitionerClinic, Pharmacy.name)
        .join(Pharmacy, Pharmacy.id == PractitionerClinic.pharmacy_id)
        .where(PractitionerClinic.practitioner_id.in_(practitioner_ids),
               PractitionerClinic.pharmacy_id.in_(pids),
               PractitionerClinic.deleted_at.is_(None))
        .order_by(Pharmacy.name))).all()
    out: dict = {}
    for link, clinic_name in rows:
        out.setdefault(link.practitioner_id, []).append({
            "pharmacy_id": str(link.pharmacy_id), "pharmacy_name": clinic_name,
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
        "pharmacy_id": str(p.pharmacy_id), "chain_id": str(p.chain_id) if p.chain_id else None,
        "user_id": str(p.user_id) if p.user_id else None,
        "user_name": login[0] if login else None, "user_email": login[1] if login else None,
        "clinics": clinics,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def shape_many(db: AsyncSession, items: list[Practitioner], pids: list[uuid.UUID],
                     chain_id: uuid.UUID) -> list[dict]:
    clinic_map = await clinics_for(db, [p.id for p in items], pids)
    logins = await login_for(db, [p.user_id for p in items if p.user_id], chain_id)
    return [shape(p, clinic_map.get(p.id, []), logins.get(p.user_id)) for p in items]
