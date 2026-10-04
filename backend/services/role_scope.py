"""Workspace-wide roles (docs/32 P0, docs/33).

A role is owned by the workspace (`roles.chain_id`) and works at every place in it.
Every role lookup goes through here so no router decides scope on its own.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.pharmacy import Pharmacy
from models.users import Role, User, UserStoreRole


async def chain_of(db: AsyncSession, pharmacy_id: uuid.UUID) -> uuid.UUID:
    """The workspace a place belongs to (every place has one — docs/33)."""
    # tenant-safe: reads only the caller's own place to learn its workspace
    return (await db.execute(select(Pharmacy.chain_id).where(Pharmacy.id == pharmacy_id))).scalar_one()


def scope_clause(pharmacy_id: uuid.UUID, chain_id: uuid.UUID):
    """SQL condition: roles usable by this place — every role of its workspace."""
    return Role.chain_id == chain_id


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


async def role_users_in_chain(db: AsyncSession, role_id: uuid.UUID) -> int:
    """How many logins hold a role anywhere (home role or any store-access row)."""
    # tenant-safe: role ids are hospital-scoped and already verified by get_role_or_404
    home = {r for r in (await db.execute(select(User.id).where(User.role_id == role_id))).scalars()}
    via = {r for r in (await db.execute(
        select(UserStoreRole.user_id).where(UserStoreRole.role_id == role_id))).scalars()}
    return len(home | via)
