"""Clinic lookups scoped to the caller's hospital (docs/32_CLINICS_SCOPE.md).

A clinic is visible to a login when it is in the same workspace as the login's current place.
Every clinic read/write goes here."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.clinics import Clinic
from services.role_scope import chain_of


def clinic_scope(pharmacy_id: uuid.UUID, chain_id: uuid.UUID):
    return Clinic.chain_id == chain_id


async def list_clinics(db: AsyncSession, pharmacy_id: uuid.UUID, include_inactive: bool = False) -> list[Clinic]:
    chain_id = await chain_of(db, pharmacy_id)
    conds = [clinic_scope(pharmacy_id, chain_id), Clinic.deleted_at.is_(None)]
    if not include_inactive:
        conds.append(Clinic.is_active)
    return list((await db.execute(select(Clinic).where(*conds).order_by(Clinic.name))).scalars().all())


async def get_clinic_or_404(db: AsyncSession, clinic_id: str, pharmacy_id: uuid.UUID) -> Clinic:
    try:
        cid = uuid.UUID(str(clinic_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Clinic not found")
    chain_id = await chain_of(db, pharmacy_id)
    clinic = (await db.execute(select(Clinic).where(
        Clinic.id == cid, clinic_scope(pharmacy_id, chain_id), Clinic.deleted_at.is_(None)))).scalar_one_or_none()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


async def name_taken(db: AsyncSession, pharmacy_id: uuid.UUID, name: str,
                     except_id: Optional[uuid.UUID] = None) -> bool:
    chain_id = await chain_of(db, pharmacy_id)
    conds = [clinic_scope(pharmacy_id, chain_id), Clinic.deleted_at.is_(None),
             func.lower(Clinic.name) == name.strip().lower()]
    if except_id:
        conds.append(Clinic.id != except_id)
    return (await db.execute(select(Clinic.id).where(*conds))).first() is not None


def shape(c: Clinic) -> dict:
    return {
        "id": str(c.id), "name": c.name, "address": c.address, "city": c.city, "state": c.state,
        "pincode": c.pincode, "phone": c.phone, "email": c.email, "registration_no": c.registration_no,
        "is_active": c.is_active, "has_pharmacy": c.linked_pharmacy_id is not None,
    }


def active_clinic_id(current_user) -> uuid.UUID:
    """The clinic the caller is working at (EMR / clinic billing). 409 with a plain next step when none is
    chosen — the login has no clinic access yet, or has not picked one."""
    if not current_user.clinic_id:
        raise HTTPException(
            status_code=409,
            detail="No clinic selected. Pick a clinic from the switcher, or ask an administrator to give you "
                   "access to one (Settings → Organisation → Clinics).")
    return uuid.UUID(str(current_user.clinic_id))


async def get_clinic_owned_or_404(db: AsyncSession, model, record_id, clinic_id: uuid.UUID, *,
                                  not_found_detail: str = "Not found", extra_conditions=None):
    """The clinic twin of `get_owned_or_404`: one row of `model` by id, only if it belongs to this clinic."""
    try:
        rid = record_id if isinstance(record_id, uuid.UUID) else uuid.UUID(str(record_id))
    except ValueError:
        raise HTTPException(status_code=404, detail=not_found_detail)
    conditions = [model.id == rid, model.clinic_id == clinic_id]
    if extra_conditions:
        conditions.extend(extra_conditions)
    row = (await db.execute(select(model).where(*conditions))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=not_found_detail)
    return row
