"""The hospital (chain) a place belongs to — created lazily, the first time a second place is added.

One function so Add Pharmacy and Add Clinic form a hospital in exactly the same way: roles and
existing clinics of the founding pharmacy move under the new hospital (nobody's access changes).
"""
from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models.chains import Chain
from models.clinics import Clinic
from models.pharmacy import Pharmacy
from services.role_scope import promote_roles_to_chain


async def ensure_chain(db: AsyncSession, pharmacy: Pharmacy, owner_user_id: uuid.UUID) -> uuid.UUID:
    """The hospital id for `pharmacy`, forming one around it first if it is still standalone."""
    if pharmacy.chain_id is not None:
        return pharmacy.chain_id
    chain = Chain(name=f"{pharmacy.name} Group", owner_user_id=owner_user_id)
    db.add(chain)
    await db.flush()
    pharmacy.chain_id = chain.id
    await promote_roles_to_chain(db, pharmacy.id, chain.id)
    # tenant-safe: only the founding pharmacy's own clinics move under the new hospital
    await db.execute(update(Clinic).where(
        Clinic.linked_pharmacy_id == pharmacy.id, Clinic.chain_id.is_(None)).values(chain_id=chain.id))
    await db.flush()
    return chain.id
