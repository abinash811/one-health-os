"""Pharmacy provisioning — the single place a new pharmacy tenant gets created.

Used by POST /auth/register (a new signup) and by main.py's startup seeder
(bootstrapping a fresh dev database). Both must produce identical, correctly
formatted data — role permissions in particular must be the flat list format
from constants.DEFAULT_ROLES, since that's what the runtime permission checks
in routers/sales_returns.py and routers/settings.py actually understand.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from constants import DEFAULT_ROLES
from models.pharmacy import Pharmacy, PharmacySettings
from models.users import Role as RoleORM, UserStoreRole

# Columns a new store's PharmacySettings must never copy from a source store,
# even when one is given (docs/15_ROADMAP.md RULE MISSES LOG, Sep 28, 2026 —
# a multi-chain persona audit found "Add Store" silently resetting every
# setting with zero carryover, the flip side of this same bug: copying
# these two specifically would be actively wrong, not just unhelpful).
# bill_sequence_number/return_sequence_number are each store's own gapless
# invoice-numbering counter — GST requires a separate series per registered
# entity, so a new store must always start its own series at 1, never
# inherit (or worse, collide with) another store's current count.
_SETTINGS_NEVER_COPY = {
    "id", "pharmacy_id", "created_at", "updated_at",
    "bill_sequence_number", "return_sequence_number",
}


async def create_pharmacy_with_defaults(
    db: AsyncSession,
    *,
    name: str,
    address: str,
    city: str,
    state: str,
    pincode: str,
    phone: str,
    email: Optional[str] = None,
    gstin: Optional[str] = None,
    drug_license_number: Optional[str] = None,
    source_settings: Optional[PharmacySettings] = None,
    chain_id: Optional[uuid.UUID] = None,
) -> Pharmacy:
    """Create a Pharmacy, its PharmacySettings, and the default role set.

    `chain_id`, when given, puts the new pharmacy in that hospital and does NOT create a
    role set — roles belong to the hospital (docs/32_CLINICS_SCOPE.md P0) and the new place
    uses the hospital's existing ones.

    Does not commit — caller controls the transaction so the pharmacy can be
    created in the same unit of work as the admin user who owns it.

    `source_settings`, when given (only `routers/chains.py`'s "Add Store"
    flow passes one — a brand-new signup via `POST /auth/register` never
    has an existing store to copy from), carries over every PharmacySettings
    field from that store EXCEPT `_SETTINGS_NEVER_COPY` above — branding,
    GST defaults, thresholds, alerts, and print/receipt preferences all
    transfer, so a chain's second store doesn't start from a blank slate an
    admin has to manually redo. Omitted/None = today's unchanged behavior,
    every field at its bare column default.
    """
    pharmacy = Pharmacy(
        name=name,
        address=address,
        city=city,
        state=state,
        pincode=pincode,
        phone=phone,
        email=email,
        gstin=gstin,
        drug_license_number=drug_license_number,
        chain_id=chain_id,
    )
    db.add(pharmacy)
    await db.flush()  # populate pharmacy.id before FK references below

    if source_settings is not None:
        copied_fields = {
            col.key: getattr(source_settings, col.key)
            for col in inspect(PharmacySettings).columns
            if col.key not in _SETTINGS_NEVER_COPY
        }
        db.add(PharmacySettings(pharmacy_id=pharmacy.id, **copied_fields))
    else:
        db.add(PharmacySettings(pharmacy_id=pharmacy.id))

    for role_def in (DEFAULT_ROLES if chain_id is None else []):
        db.add(RoleORM(
            pharmacy_id=pharmacy.id,
            name=role_def["name"],
            description=role_def.get("display_name", role_def["name"]),
            permissions=role_def["permissions"],
            is_system_role=role_def.get("is_default", False),
        ))

    await db.flush()
    return pharmacy


async def sync_user_store_role(
    db: AsyncSession, *, user_id: uuid.UUID, pharmacy_id: uuid.UUID, role_id: uuid.UUID,
) -> None:
    """Every place a `User` row gets created must call this too, so
    `user_store_roles` (docs/26_MULTI_CHAIN_SCOPE.md) stays a complete,
    correct mirror of `users.pharmacy_id`/`role_id` going forward — not
    just backfilled once at migration time. Nothing reads this table yet;
    login/permission checks still use the columns on `users` directly."""
    db.add(UserStoreRole(user_id=user_id, pharmacy_id=pharmacy_id, role_id=role_id))
    await db.flush()
