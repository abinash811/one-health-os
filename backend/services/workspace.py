"""The workspace (hospital) as the boundary for identity — logins, Team, audit (docs/33_WORKSPACE_SCOPE.md W3).

One place decides "which workspace is the caller in" and "is this login in it", so no router repeats it.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models.users import User as UserORM
from services.role_scope import chain_of


async def caller_workspace(db: AsyncSession, current_user) -> uuid.UUID:
    """The caller's workspace id. Every login has one since W1; the fallback only covers a session whose
    user row has not been backfilled yet."""
    if current_user.chain_id:
        return uuid.UUID(str(current_user.chain_id))
    chain_id = await chain_of(db, uuid.UUID(current_user.pharmacy_id))
    if chain_id is None:
        raise HTTPException(status_code=409, detail="Your account is not part of a workspace yet")
    return chain_id


async def list_workspace_users(db: AsyncSession, chain_id: uuid.UUID) -> list[UserORM]:
    rows = await db.execute(
        select(UserORM).options(joinedload(UserORM.role)).where(UserORM.chain_id == chain_id)
        .order_by(UserORM.created_at))
    return list(rows.scalars().unique().all())


async def get_workspace_user_or_404(db: AsyncSession, user_id: str, chain_id: uuid.UUID) -> UserORM:
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")
    user = (await db.execute(
        select(UserORM).options(joinedload(UserORM.role)).where(
            UserORM.id == uid, UserORM.chain_id == chain_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
