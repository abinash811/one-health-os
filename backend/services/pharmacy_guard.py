"""What must be true before a pharmacy can be archived (docs/32 follow-up, Oct 4, 2026).

Archiving is soft — the pharmacy's bills, stock and history stay for audits — but nobody may be left working
in a pharmacy that is switched off, and unfinished work must not be orphaned. Returns a plain-language reason,
or None when the pharmacy is clear. Everything here is set-based (no query per person)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import OPEN_BILL_STATUSES, PURCHASE_STATUS_DRAFT
from models.billing import Bill
from models.pharmacy import Pharmacy
from models.purchases import Purchase
from models.users import User as UserORM, UserStoreRole


def _has_other_active_store(pharmacy_id: uuid.UUID):
    """SQL: this login holds a grant at a DIFFERENT, active pharmacy."""
    return exists().where(
        UserStoreRole.user_id == UserORM.id, UserStoreRole.pharmacy_id != pharmacy_id,
        UserStoreRole.pharmacy_id == Pharmacy.id, Pharmacy.is_active)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


async def archive_blocker(db: AsyncSession, pharmacy: Pharmacy) -> Optional[str]:
    # tenant-safe: every query below is filtered to the pharmacy being archived, already workspace-checked
    active = (await db.execute(select(func.count()).select_from(Pharmacy).where(
        Pharmacy.chain_id == pharmacy.chain_id, Pharmacy.is_active))).scalar_one()
    if active <= 1:
        return "it is the only active pharmacy of your workspace"
    bills = (await db.execute(select(func.count()).select_from(Bill).where(
        Bill.pharmacy_id == pharmacy.id, Bill.status.in_(OPEN_BILL_STATUSES),
        Bill.deleted_at.is_(None)))).scalar_one()
    if bills:
        them = "it" if bills == 1 else "them"
        return f"{_plural(bills, 'unfinished bill', 'unfinished bills')} — finish or delete {them} first"
    drafts = (await db.execute(select(func.count()).select_from(Purchase).where(
        Purchase.pharmacy_id == pharmacy.id, Purchase.status == PURCHASE_STATUS_DRAFT,
        Purchase.deleted_at.is_(None)))).scalar_one()
    if drafts:
        them = "it" if drafts == 1 else "them"
        return f"{_plural(drafts, 'draft purchase', 'draft purchases')} — confirm or delete {them} first"
    working_here = UserORM.pharmacy_id == pharmacy.id  # workspace-safe: people working at this pharmacy
    stuck = (await db.execute(select(func.count()).select_from(UserORM).where(
        working_here, UserORM.is_active, ~_has_other_active_store(pharmacy.id)))).scalar_one()
    if stuck:
        who = "person can" if stuck == 1 else "people can"
        return f"{stuck} {who} open no other pharmacy — give them access to another one first"
    return None


async def move_people_off(db: AsyncSession, pharmacy_id: uuid.UUID) -> None:
    """Everyone whose active pharmacy was just archived lands on another one they can open (taking their role
    there) — one query for the people and their candidate grants, not one per person."""
    rows = (await db.execute(
        select(UserORM, UserStoreRole)
        .join(UserStoreRole, UserStoreRole.user_id == UserORM.id)
        .join(Pharmacy, Pharmacy.id == UserStoreRole.pharmacy_id)
        .where(UserORM.pharmacy_id == pharmacy_id,  # workspace-safe: working here
               UserStoreRole.pharmacy_id != pharmacy_id, Pharmacy.is_active)
        .order_by(UserStoreRole.created_at))).all()
    moved: set[uuid.UUID] = set()
    for person, grant in rows:
        if person.id in moved:
            continue
        person.pharmacy_id, person.role_id = grant.pharmacy_id, grant.role_id
        moved.add(person.id)
    await db.flush()
