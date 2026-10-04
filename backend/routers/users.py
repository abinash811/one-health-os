from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from deps import DbSession
from models.pharmacy import Pharmacy as PharmacyORM
from models.users import AuditLog, Role as RoleORM, User as UserORM, UserStoreRole
from routers.auth_helpers import (
    User, get_current_user, hash_password, require_admin_or_super, verify_password,
)
from services.provisioning import sync_user_store_role
from services.role_scope import find_role
from services.workspace import caller_workspace, get_workspace_user_or_404, list_workspace_users

router = APIRouter(prefix="/api", tags=["users"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    # Mirrors settings.py/customers.py's identical local helper — no
    # cross-router import exists anywhere in this codebase, each router
    # keeps its own copy. This router had zero audit trail at all before
    # Sep 16, 2026 (found by scripts/check_audit_log_coverage.py) — staff
    # account create/edit/deactivate and admin password resets left no
    # record of who did it.
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    # docs/14_SECURITY.md KNOWN GAPS #2 — same rule as auth.py::UserCreate.
    password: str = Field(min_length=6)
    role: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class AdminResetPassword(BaseModel):
    new_password: str


def _user_response(user: UserORM) -> dict:
    """Format a UserORM row for API response (excludes password_hash)."""
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.name,
        "role_id": str(user.role_id),
        "pharmacy_id": str(user.pharmacy_id),
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        # Existed on the model since day one but nothing ever set it
        # (fixed in auth.py's login()) or returned it here — every
        # member's last-login was invisible regardless of real usage.
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get("/users")
async def get_all_users(current_user: User = Depends(get_current_user),
                        db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    users = await list_workspace_users(db, await caller_workspace(db, current_user))
    return [_user_response(u) for u in users]


@router.post("/users")
async def create_user(user_data: UserCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)

    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    role = await find_role(db, pharmacy_id, user_data.role)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{user_data.role}' not found")

    workspace_id = await caller_workspace(db, current_user)
    existing = await db.execute(
        select(UserORM).where(UserORM.chain_id == workspace_id, UserORM.email == user_data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = UserORM(
        pharmacy_id=pharmacy_id,
        chain_id=workspace_id,
        role_id=role.id,
        is_admin=user_data.is_admin,
        name=user_data.name,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
    )
    db.add(user)
    await db.flush()
    await sync_user_store_role(db, user_id=user.id, pharmacy_id=pharmacy_id, role_id=role.id)
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "user", user.id,
        {"name": user.name, "email": user.email, "role": user_data.role, "is_admin": user.is_admin}, db,
        ip_address=_client_ip(request),
    )
    await db.flush()

    result = await db.execute(
        # tenant-safe: user just created in this same request
        select(UserORM).options(joinedload(UserORM.role)).where(UserORM.id == user.id)
    )
    return _user_response(result.scalar_one())


@router.get("/users/{user_id}")
async def get_user(user_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    user = await get_workspace_user_or_404(db, user_id, await caller_workspace(db, current_user))
    return _user_response(user)


@router.put("/users/{user_id}")
async def update_user(user_id: str, user_update: UserUpdate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    workspace_id = await caller_workspace(db, current_user)
    user = await get_workspace_user_or_404(db, user_id, workspace_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_values = {"name": user.name, "email": user.email, "role": user.role.name,
                  "is_active": user.is_active, "is_admin": user.is_admin}

    if user_update.role is not None:
        role = await find_role(db, user.pharmacy_id, user_update.role)
        if not role:
            raise HTTPException(status_code=400, detail=f"Role '{user_update.role}' not found")
        user.role_id = role.id

    if user_update.email is not None and user_update.email != user.email:
        dup = await db.execute(
            select(UserORM).where(
                UserORM.chain_id == workspace_id,
                UserORM.email == user_update.email)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = user_update.email

    if user_update.name is not None:
        user.name = user_update.name
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    if user_update.is_admin is not None and user_update.is_admin != user.is_admin:
        if not user_update.is_admin and str(user.id) == current_user.id:
            raise HTTPException(status_code=400, detail="You can't remove your own admin access")
        user.is_admin = user_update.is_admin

    await db.flush()
    await db.refresh(user, attribute_names=["role"])
    new_values = {"name": user.name, "email": user.email, "role": user.role.name,
                  "is_active": user.is_active, "is_admin": user.is_admin}
    if new_values != old_values:
        await _record_audit(
            uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "update", "user", user.id,
            new_values, db, old_values=old_values, ip_address=_client_ip(request),
        )
        await db.flush()
    result = await db.execute(
        # tenant-safe: user already scoped above
        select(UserORM).options(joinedload(UserORM.role)).where(UserORM.id == user.id)
    )
    return _user_response(result.scalar_one())


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: str, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user = await get_workspace_user_or_404(
        db, user_id, await caller_workspace(db, current_user))

    user.is_active = False
    await db.flush()
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "deactivate", "user", user.id,
        {"is_active": False}, db, old_values={"is_active": True}, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "User deactivated successfully"}


@router.put("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, password_data: AdminResetPassword, request: Request,
                               current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Admin/Super Admin sets a new password directly for another user —
    no email/token infra needed, unlike a self-service "forgot password"
    flow (still separately planned). Closes a real gap: a locked-out
    cashier previously had no way back in short of a direct DB edit.
    """
    await require_admin_or_super(current_user, db)
    user = await get_workspace_user_or_404(
        db, user_id, await caller_workspace(db, current_user))

    user.password_hash = hash_password(password_data.new_password)
    await db.flush()
    # No password hash/value in new_values — this row only needs to answer
    # "who reset whose password, when," never carry a credential.
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "admin_reset_password", "user", user.id,
        {"reset_by": current_user.id}, db, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Password reset successfully"}


@router.put("/users/me/change-password")
async def change_password(password_data: ChangePassword, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # permission-exempt: self-service — any authenticated user may change their own
    # password, gated by knowing the current password, not by role
    # audit-exempt: self-initiated password change with no privilege change;
    # login/auth events already have their own trail (_record_login_event)
    # tenant-safe: self-scoped, id is the caller's own JWT subject
    result = await db.execute(select(UserORM).where(UserORM.id == uuid.UUID(current_user.id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(password_data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(password_data.new_password)
    await db.flush()
    return {"message": "Password changed successfully"}


class SwitchStore(BaseModel):
    pharmacy_id: str


@router.get("/users/me/stores")
async def get_my_stores(current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Every store this person can access, for the sidebar switcher —
    docs/26_MULTI_CHAIN_SCOPE.md Step 2. Always returns at least one row
    (today's single-store reality); the switcher shows even then, per
    direct instruction, not conditionally hidden for a single-store
    account. `gstin` (added Sep 27, 2026) lets the frontend pre-filter
    which stores are actually valid stock-transfer destinations — POST
    /stock-transfers only allows transfers between stores with matching
    GSTINs (Section 6 #5), so the picker can hide the rest up front
    instead of letting someone fill in a whole transfer just to be
    rejected at submit.
    # permission-exempt: self-service, scoped to the caller's own access
    """
    result = await db.execute(
        select(UserStoreRole, PharmacyORM.name, RoleORM.name, PharmacyORM.gstin)
        .join(PharmacyORM, PharmacyORM.id == UserStoreRole.pharmacy_id)
        .join(RoleORM, RoleORM.id == UserStoreRole.role_id)
        .where(UserStoreRole.user_id == uuid.UUID(current_user.id))
        .order_by(PharmacyORM.name)
    )
    current_pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    rows = result.all()
    if not rows:
        # A login created before every creation path wrote its store-access row (e.g. by seed_admin.py)
        # still belongs to its home store — never answer "no stores" for someone who is signed in to one.
        home = (await db.execute(
            select(PharmacyORM.name, PharmacyORM.gstin).where(
                PharmacyORM.id == current_pharmacy_id))).one()  # tenant-safe: the caller's own store
        return [{"pharmacy_id": str(current_pharmacy_id), "pharmacy_name": home[0],
                 "role_name": current_user.role, "is_active": True, "gstin": home[1]}]
    return [
        {
            "pharmacy_id": str(usr.pharmacy_id),
            "pharmacy_name": pharmacy_name,
            "role_name": role_name,
            "is_active": usr.pharmacy_id == current_pharmacy_id,
            "gstin": gstin,
        }
        for usr, pharmacy_name, role_name, gstin in rows
    ]


@router.post("/users/me/switch-store")
async def switch_store(body: SwitchStore, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Makes another store this person already has access to their active
    one. Not a login/session change — `users.pharmacy_id`/`role_id` are
    read fresh from the DB on every request (routers/auth_helpers.py's
    `get_current_user`), so updating those two columns *is* the switch;
    no new token needs issuing.
    # permission-exempt: self-service, but only into a store this exact
    # user already has a real user_store_roles row for — checked below,
    # not inferred from being logged in at all.
    """
    target_pharmacy_id = uuid.UUID(body.pharmacy_id)
    result = await db.execute(
        select(UserStoreRole).where(
            UserStoreRole.user_id == uuid.UUID(current_user.id),
            UserStoreRole.pharmacy_id == target_pharmacy_id,
        )
    )
    access = result.scalar_one_or_none()
    if not access:
        raise HTTPException(status_code=403, detail="You do not have access to that store")

    user_result = await db.execute(
        # tenant-safe: id is the caller's own JWT subject, not user-supplied
        select(UserORM).where(UserORM.id == uuid.UUID(current_user.id)))
    user = user_result.scalar_one()
    old_pharmacy_id = user.pharmacy_id
    user.pharmacy_id = access.pharmacy_id
    user.role_id = access.role_id
    await db.flush()
    await _record_audit(
        access.pharmacy_id, uuid.UUID(current_user.id), "switch_store", "user", user.id,
        {"pharmacy_id": str(access.pharmacy_id)}, db,
        old_values={"pharmacy_id": str(old_pharmacy_id)}, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Switched store successfully", "pharmacy_id": str(access.pharmacy_id)}


class GrantStoreAccess(BaseModel):
    pharmacy_id: str
    role: str


async def _same_chain_or_self(target_pharmacy_id: uuid.UUID, admin_pharmacy_id: uuid.UUID, db: AsyncSession) -> None:
    """A store can only be granted if it's the admin's own pharmacy or
    another store in the same chain — never an unrelated pharmacy
    elsewhere in the system (docs/26_MULTI_CHAIN_SCOPE.md)."""
    if target_pharmacy_id == admin_pharmacy_id:
        return
    result = await db.execute(
        select(PharmacyORM.chain_id).where(PharmacyORM.id == admin_pharmacy_id))
    admin_chain_id = result.scalar_one_or_none()
    if admin_chain_id is None:
        raise HTTPException(status_code=400, detail="Your pharmacy is not part of a workspace yet")
    # chain-scope-safe: single-target membership gate before a grant, not a multi-pharmacy rollup
    target_result = await db.execute(
        select(PharmacyORM).where(
            PharmacyORM.id == target_pharmacy_id,
            PharmacyORM.chain_id == admin_chain_id))  # chain-scope-safe: see above
    if not target_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="That place is not in your workspace")


@router.get("/users/{user_id}/store-access")
async def get_user_store_access(user_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    await get_workspace_user_or_404(
        db, user_id, await caller_workspace(db, current_user))

    result = await db.execute(
        select(UserStoreRole, PharmacyORM.name, RoleORM.name)
        .join(PharmacyORM, PharmacyORM.id == UserStoreRole.pharmacy_id)
        .join(RoleORM, RoleORM.id == UserStoreRole.role_id)
        .where(UserStoreRole.user_id == uuid.UUID(user_id))
        .order_by(PharmacyORM.name)
    )
    return [
        {"pharmacy_id": str(usr.pharmacy_id), "pharmacy_name": pharmacy_name, "role_name": role_name}
        for usr, pharmacy_name, role_name in result.all()
    ]


@router.post("/users/{user_id}/store-access")
async def grant_user_store_access(user_id: str, body: GrantStoreAccess, request: Request,
                                  current_user: User = Depends(get_current_user),
                                  db: AsyncSession = DbSession):
    """Grants (or updates the role for) one of the admin's team members
    at another store in the same chain. The target user must already be
    one of the admin's own team members — this never looks up an
    arbitrary user elsewhere in the system."""
    await require_admin_or_super(current_user, db)
    admin_pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    target_user = await get_workspace_user_or_404(
        db, user_id, await caller_workspace(db, current_user))

    target_pharmacy_id = uuid.UUID(body.pharmacy_id)
    await _same_chain_or_self(target_pharmacy_id, admin_pharmacy_id, db)

    role = await find_role(db, target_pharmacy_id, body.role)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role}' not found at that store")

    existing_result = await db.execute(
        select(UserStoreRole).where(
            UserStoreRole.user_id == target_user.id, UserStoreRole.pharmacy_id == target_pharmacy_id))
    existing = existing_result.scalar_one_or_none()
    if existing:
        existing.role_id = role.id
    else:
        db.add(UserStoreRole(user_id=target_user.id, pharmacy_id=target_pharmacy_id, role_id=role.id))
    await db.flush()

    await _record_audit(
        admin_pharmacy_id, uuid.UUID(current_user.id), "grant_store_access", "user", target_user.id,
        {"pharmacy_id": str(target_pharmacy_id), "role": body.role}, db, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Store access granted"}


@router.delete("/users/{user_id}/store-access/{pharmacy_id}")
async def revoke_user_store_access(user_id: str, pharmacy_id: str, request: Request,
                                   current_user: User = Depends(get_current_user),
                                   db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    admin_pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    target_user = await get_workspace_user_or_404(
        db, user_id, await caller_workspace(db, current_user))

    target_pharmacy_id = uuid.UUID(pharmacy_id)
    if target_pharmacy_id == target_user.pharmacy_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot revoke access to this person's current active store — switch them to another store first")

    count_result = await db.execute(
        select(UserStoreRole).where(UserStoreRole.user_id == target_user.id))
    all_grants = count_result.scalars().all()
    if len(all_grants) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove someone's only store access")

    grant = next((g for g in all_grants if g.pharmacy_id == target_pharmacy_id), None)
    if not grant:
        raise HTTPException(status_code=404, detail="No such store access grant")

    await db.delete(grant)
    await db.flush()
    await _record_audit(
        admin_pharmacy_id, uuid.UUID(current_user.id), "revoke_store_access", "user", target_user.id,
        {"pharmacy_id": str(target_pharmacy_id)}, db, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Store access revoked"}
