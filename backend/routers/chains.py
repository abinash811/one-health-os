"""Chain / multi-store management — docs/26_MULTI_CHAIN_SCOPE.md Step 3
(added under Settings, Sep 26, 2026, direct instruction, right after the
Step 2 store switcher shipped).

A `Chain` is created the moment an admin adds their pharmacy's first
additional store — not upfront at signup. Every pharmacy created via
`POST /auth/register` stays `chain_id = NULL` (a plain standalone store)
until this happens. The admin who creates the new store is immediately
granted access to it too (their own `user_store_roles` row) — nobody
should have to separately grant themselves access to a store they just
created.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.pharmacy import Pharmacy as PharmacyORM, PharmacySettings as PharmacySettingsORM
from models.users import AuditLog
from routers.auth_helpers import User, get_current_user, has_permission, resolve_chain_scope_pids
from services.pharmacy_guard import archive_blocker, move_people_off
from services.provisioning import create_pharmacy_with_defaults, sync_user_store_role

router = APIRouter(prefix="/api", tags=["chains"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        ip_address=ip_address,
    ))


def _store_row(s: PharmacyORM) -> dict:
    return {
        "pharmacy_id": str(s.id), "name": s.name, "city": s.city, "state": s.state, "address": s.address,
        "pincode": s.pincode, "phone": s.phone, "email": s.email, "gstin": s.gstin,
        "drug_license_number": s.drug_license_number, "is_active": s.is_active,
    }


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=10)
    email: Optional[str] = Field(default=None, max_length=200)
    gstin: Optional[str] = Field(default=None, max_length=15)
    drug_license_number: Optional[str] = Field(default=None, max_length=50)
    is_active: Optional[bool] = None

    @field_validator("name", "address", "city", "state", "pincode", "phone", "email", "gstin", "drug_license_number")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("name", "address", "city", "state", "pincode", "phone")
    @classmethod
    def _required_ones_not_blank(cls, v):
        if v is not None and v == "":
            raise ValueError("This field cannot be blank")
        return v

    @field_validator("pincode")
    @classmethod
    def _six_digits(cls, v):
        if v is not None and not re.fullmatch(r"\d{6}", v):
            raise ValueError("Pincode must be 6 digits")
        return v

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        return v.upper() if v else None


class StoreCreate(BaseModel):
    name: str
    address: str
    city: str
    state: str
    pincode: str
    phone: str
    email: Optional[str] = None
    gstin: Optional[str] = None
    drug_license_number: Optional[str] = None


@router.get("/pharmacies/stores")
async def get_chain_stores(include_archived: bool = False, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Every store in the caller's chain, including their own — for the
    Settings "Stores" tab and the Team page's per-user store-access
    picker. A workspace with one pharmacy just gets that one back.
    # permission-exempt: read-only, scoped to the caller's own workspace
    """
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(select(PharmacyORM).where(PharmacyORM.id == pharmacy_id))
    pharmacy = result.scalar_one()

    query = select(PharmacyORM).where(PharmacyORM.chain_id == pharmacy.chain_id)
    if not include_archived:
        query = query.where(PharmacyORM.is_active)   # archived pharmacies drop out of every picker
    stores = (await db.execute(query.order_by(PharmacyORM.name))).scalars().all()

    return [_store_row(s) for s in stores]


@router.post("/pharmacies/stores")
async def create_chain_store(body: StoreCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Adds a new pharmacy (needs the `pharmacies:create` tick). If the caller's pharmacy isn't in a chain yet,
    creates one now (this is the one and only place a Chain gets created)
    and puts the caller's own existing pharmacy in it too, alongside the
    new one — both real stores in the same chain from this point on."""
    if not await has_permission(current_user, "pharmacies:create", db):
        raise HTTPException(status_code=403, detail="Your role does not have the 'pharmacies:create' permission")
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(select(PharmacyORM).where(PharmacyORM.id == pharmacy_id))
    pharmacy = result.scalar_one()

    # Fixed Sep 28, 2026 (docs/15_ROADMAP.md RULE MISSES LOG): a new store
    # used to always get bare PharmacySettings defaults, silently discarding
    # the admin's own branding/GST/threshold setup with no warning. Copy the
    # caller's own current settings onto the new store instead (excluding
    # per-store invoice-numbering counters — see
    # services/provisioning.py's _SETTINGS_NEVER_COPY).
    settings_result = await db.execute(
        select(PharmacySettingsORM).where(PharmacySettingsORM.pharmacy_id == pharmacy_id))
    source_settings = settings_result.scalar_one_or_none()

    new_store = await create_pharmacy_with_defaults(
        db, name=body.name, address=body.address, city=body.city, state=body.state,
        pincode=body.pincode, phone=body.phone, email=body.email, gstin=body.gstin,
        drug_license_number=body.drug_license_number, source_settings=source_settings,
        chain_id=pharmacy.chain_id,
    )
    await db.flush()

    # The creator gets the role they already hold (roles are hospital-wide) — creating a pharmacy
    # never promotes anyone to administrator.
    await sync_user_store_role(
        db, user_id=uuid.UUID(current_user.id), pharmacy_id=new_store.id, role_id=uuid.UUID(current_user.role_id))

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "store", new_store.id,
        {"name": new_store.name, "city": new_store.city}, db, ip_address=_client_ip(request),
    )
    await db.flush()

    return {"pharmacy_id": str(new_store.id), "name": new_store.name, "chain_id": str(pharmacy.chain_id)}


@router.put("/pharmacies/stores/{store_id}")
async def update_chain_store(store_id: str, body: StoreUpdate, request: Request,
                             current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Edit a pharmacy's details, or archive / restore it (`is_active`). Needs `pharmacies:edit`; only pharmacies
    of the caller's workspace — and, unless the caller holds every permission, only ones they can open.
    Archiving is soft and refused (409, plain reason) while unfinished work or stranded people remain."""
    if not await has_permission(current_user, "pharmacies:edit", db):
        raise HTTPException(status_code=403, detail="Your role does not have the 'pharmacies:edit' permission")
    try:
        target_id = uuid.UUID(store_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    own = (await db.execute(select(PharmacyORM).where(
        PharmacyORM.id == uuid.UUID(current_user.pharmacy_id)))).scalar_one()
    store = (await db.execute(select(PharmacyORM).where(  # tenant-safe: also matched to the caller's workspace
        PharmacyORM.id == target_id, PharmacyORM.chain_id == own.chain_id))).scalar_one_or_none()
    if store is None:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    if not await has_permission(current_user, "*", db):
        if target_id not in await resolve_chain_scope_pids(current_user, "chain", db):
            raise HTTPException(status_code=403, detail="You don't have access to that pharmacy")

    changes = body.model_dump(exclude_unset=True)
    for key in ("name", "address", "city", "state", "pincode", "phone", "is_active"):
        if key in changes and changes[key] is None:
            changes.pop(key)
    archiving = changes.get("is_active") is False and store.is_active
    if archiving:
        reason = await archive_blocker(db, store)
        if reason:
            raise HTTPException(status_code=409, detail=f"Can't archive {store.name}: {reason}")
    old = {k: getattr(store, k) for k in changes}
    for key, value in changes.items():
        setattr(store, key, value)
    await db.flush()
    if archiving:
        await move_people_off(db, store.id)
    restoring = changes.get("is_active") is True and old.get("is_active") is False
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id),
        "archive" if archiving else ("restore" if restoring else "update"),
        "store", store.id, dict(changes), db, ip_address=_client_ip(request),
    )
    await db.flush()
    return _store_row(store)
