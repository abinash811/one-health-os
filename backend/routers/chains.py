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

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.chains import Chain as ChainORM
from models.pharmacy import Pharmacy as PharmacyORM, PharmacySettings as PharmacySettingsORM
from models.users import AuditLog, Role as RoleORM
from routers.auth_helpers import User, get_current_user, require_admin_or_super
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
async def get_chain_stores(current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Every store in the caller's chain, including their own — for the
    Settings "Stores" tab and the Team page's per-user store-access
    picker. A standalone (non-chain) pharmacy just gets its one store
    back, same shape either way.
    # permission-exempt: read-only, scoped to the caller's own chain (or
    # their own single pharmacy if not in one)
    """
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(select(PharmacyORM).where(PharmacyORM.id == pharmacy_id))
    pharmacy = result.scalar_one()

    if pharmacy.chain_id is None:
        stores = [pharmacy]
    else:
        result = await db.execute(
            select(PharmacyORM).where(PharmacyORM.chain_id == pharmacy.chain_id)
            .order_by(PharmacyORM.name)
        )
        stores = result.scalars().all()

    return [
        {"pharmacy_id": str(s.id), "name": s.name, "city": s.city, "state": s.state}
        for s in stores
    ]


@router.post("/pharmacies/stores")
async def create_chain_store(body: StoreCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Adds a new store. If the caller's pharmacy isn't in a chain yet,
    creates one now (this is the one and only place a Chain gets created)
    and puts the caller's own existing pharmacy in it too, alongside the
    new one — both real stores in the same chain from this point on."""
    await require_admin_or_super(current_user, db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(select(PharmacyORM).where(PharmacyORM.id == pharmacy_id))
    pharmacy = result.scalar_one()

    if pharmacy.chain_id is None:
        chain = ChainORM(name=f"{pharmacy.name} Group", owner_user_id=uuid.UUID(current_user.id))
        db.add(chain)
        await db.flush()
        pharmacy.chain_id = chain.id
    else:
        chain = None  # already in a chain, nothing to create

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
    )
    new_store.chain_id = pharmacy.chain_id
    await db.flush()

    admin_role_result = await db.execute(
        select(RoleORM).where(RoleORM.pharmacy_id == new_store.id, RoleORM.name == "admin"))
    admin_role = admin_role_result.scalar_one()
    await sync_user_store_role(
        db, user_id=uuid.UUID(current_user.id), pharmacy_id=new_store.id, role_id=admin_role.id)

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "store", new_store.id,
        {"name": new_store.name, "city": new_store.city}, db, ip_address=_client_ip(request),
    )
    await db.flush()

    return {"pharmacy_id": str(new_store.id), "name": new_store.name, "chain_id": str(pharmacy.chain_id)}
