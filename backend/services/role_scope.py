"""Hospital-wide roles (docs/32_CLINICS_SCOPE.md, phase P0).

A role is owned by the hospital (`roles.chain_id`) and works at every place in it.
A standalone pharmacy (no hospital yet) keeps its own roles (`chain_id` NULL).
Every role lookup goes through here so no router decides scope on its own.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.pharmacy import Pharmacy
from models.users import Role, User, UserStoreRole


async def chain_of(db: AsyncSession, pharmacy_id: uuid.UUID) -> Optional[uuid.UUID]:
    # tenant-safe: reads only the caller's own place to learn its hospital
    return (await db.execute(
        select(Pharmacy.chain_id).where(Pharmacy.id == pharmacy_id))).scalar_one_or_none()


def scope_clause(pharmacy_id: uuid.UUID, chain_id: Optional[uuid.UUID]):
    """SQL condition: roles usable by this place."""
    if chain_id is not None:
        return Role.chain_id == chain_id
    return and_(Role.pharmacy_id == pharmacy_id, Role.chain_id.is_(None))


async def find_role(db: AsyncSession, pharmacy_id: uuid.UUID, name: str,
                    *, active_only: bool = True) -> Optional[Role]:
    chain_id = await chain_of(db, pharmacy_id)
    conds = [scope_clause(pharmacy_id, chain_id), Role.name == name]
    if active_only:
        conds.append(Role.is_active)
    return (await db.execute(select(Role).where(*conds))).scalars().first()


async def list_roles(db: AsyncSession, pharmacy_id: uuid.UUID) -> list[Role]:
    chain_id = await chain_of(db, pharmacy_id)
    return list((await db.execute(select(Role).where(
        scope_clause(pharmacy_id, chain_id), Role.is_active))).scalars().all())


async def get_role_or_404(db: AsyncSession, role_id: str, pharmacy_id: uuid.UUID,
                          detail: str = "Role not found") -> Role:
    try:
        rid = uuid.UUID(str(role_id))
    except ValueError:
        raise HTTPException(status_code=404, detail=detail)
    chain_id = await chain_of(db, pharmacy_id)
    role = (await db.execute(select(Role).where(
        Role.id == rid, scope_clause(pharmacy_id, chain_id)))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail=detail)
    return role


async def promote_roles_to_chain(db: AsyncSession, pharmacy_id: uuid.UUID,
                                 chain_id: uuid.UUID) -> None:
    """A standalone pharmacy just became part of a hospital: its roles now belong to
    the hospital. Nobody's permissions change — same rows, new owner."""
    # tenant-safe: scoped to the one pharmacy that is being promoted
    await db.execute(update(Role).where(
        Role.pharmacy_id == pharmacy_id, Role.chain_id.is_(None)).values(chain_id=chain_id))


async def role_users_in_chain(db: AsyncSession, role_id: uuid.UUID) -> int:
    """How many logins hold a role anywhere (home role or any store-access row)."""
    # tenant-safe: role ids are hospital-scoped and already verified by get_role_or_404
    home = {r for r in (await db.execute(select(User.id).where(User.role_id == role_id))).scalars()}
    via = {r for r in (await db.execute(
        select(UserStoreRole.user_id).where(UserStoreRole.role_id == role_id))).scalars()}
    return len(home | via)
