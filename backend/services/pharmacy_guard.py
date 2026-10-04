"""What must be true before a pharmacy can be archived (docs/32 follow-up, Oct 4, 2026).

Archiving is soft — the pharmacy's bills, stock and history stay for audits — but nobody may be left working
in a pharmacy that is switched off, and unfinished work must not be orphaned. Returns a plain-language reason,
or None when the pharmacy is clear."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.billing import Bill
from models.pharmacy import Pharmacy
from models.purchases import Purchase
from models.users import User as UserORM, UserStoreRole

OPEN_BILL_STATUSES = ("draft", "parked")   # 'parked' is stored as 'draft' (routers/billing.py)


async def other_active_store_for(db: AsyncSession, user_id: uuid.UUID, pharmacy_id: uuid.UUID):
    """A different, active pharmacy this login can open — their grant there — or None."""
    return (await db.execute(
        select(UserStoreRole).join(Pharmacy, Pharmacy.id == UserStoreRole.pharmacy_id)
        .where(UserStoreRole.user_id == user_id, UserStoreRole.pharmacy_id != pharmacy_id, Pharmacy.is_active)
        .limit(1))).scalar_one_or_none()


async def archive_blocker(db: AsyncSession, pharmacy: Pharmacy) -> Optional[str]:
    # tenant-safe: every query below is filtered to the pharmacy being archived, already workspace-checked
    active = (await db.execute(select(func.count()).select_from(Pharmacy).where(
        Pharmacy.chain_id == pharmacy.chain_id, Pharmacy.is_active))).scalar_one()
    if active <= 1:
        return "it is the only active pharmacy of your workspace"
    bills = (await db.execute(select(func.count()).select_from(Bill).where(
        Bill.pharmacy_id == pharmacy.id, Bill.status.in_(OPEN_BILL_STATUSES)))).scalar_one()
    if bills:
        many = bills != 1
        return f"{bills} unfinished bill{'s' if many else ''} — finish or delete {'them' if many else 'it'} first"
    drafts = (await db.execute(select(func.count()).select_from(Purchase).where(
        Purchase.pharmacy_id == pharmacy.id, Purchase.status == "draft"))).scalar_one()
    if drafts:
        many = drafts != 1
        return f"{drafts} draft purchase{'s' if many else ''} — confirm or delete {'them' if many else 'it'} first"
    stuck = 0
    for (uid,) in (await db.execute(select(UserORM.id).where(
            UserORM.pharmacy_id == pharmacy.id, UserORM.is_active))).all():  # workspace-safe: people working here
        if await other_active_store_for(db, uid, pharmacy.id) is None:
            stuck += 1
    if stuck:
        return (f"{stuck} {'people' if stuck != 1 else 'person'} can open no other pharmacy — "
                "give them access to another one first")
    return None


async def move_people_off(db: AsyncSession, pharmacy_id: uuid.UUID) -> None:
    """Everyone whose active pharmacy was just archived lands on another one they can open (taking their role there)."""
    for person in (await db.execute(select(UserORM).where(
            UserORM.pharmacy_id == pharmacy_id))).scalars().all():  # workspace-safe: people working here
        grant = await other_active_store_for(db, person.id, pharmacy_id)
        if grant is not None:
            person.pharmacy_id = grant.pharmacy_id
            person.role_id = grant.role_id
    await db.flush()
