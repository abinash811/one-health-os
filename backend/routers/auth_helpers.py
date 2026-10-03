"""Shared auth helpers — JWT, password helpers, and get_current_user dependency."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, Request
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config import settings
from deps import DbSession
from models.users import Role as RoleORM, User as UserORM

# ── security config ────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY: str = settings.SECRET_KEY
ALGORITHM: str = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES


# ── current-user Pydantic model (carried through every request) ────────────────
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: str        # role name — for checks like: current_user.role == "admin"
    role_id: str
    pharmacy_id: str
    is_active: bool = True
    is_admin: bool = False


# ── helpers ────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = DbSession,
) -> User:
    token = session_token
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(
        select(UserORM)
        .options(joinedload(UserORM.role))
        .where(UserORM.id == uuid.UUID(user_id))
    )
    user_row = result.scalar_one_or_none()
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    if not user_row.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    return User(
        id=str(user_row.id),
        email=user_row.email,
        name=user_row.name,
        role=user_row.role.name,
        role_id=str(user_row.role_id),
        pharmacy_id=str(user_row.pharmacy_id),
        is_active=user_row.is_active,
        is_admin=user_row.is_admin,
    )


def paginate_response(items: list, page: int, page_size: int, total: int) -> dict:
    return {
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        },
    }


async def get_owned_or_404(
    db: AsyncSession,
    model,
    record_id,
    pharmacy_id: uuid.UUID,
    not_found_detail: str = "Not found",
    extra_conditions: Optional[list] = None,
):
    """Fetch a single row by primary key, scoped to the caller's own
    pharmacy — the ONLY sanctioned way to look up a pharmacy-owned record
    by ID anywhere in this codebase.

    Found Sep 12, 2026: nearly every "get/update/delete by id" endpoint in
    the app looked up its row with `select(Model).where(Model.id == id)`
    alone — no pharmacy_id check. Proved live: a freshly-registered,
    completely separate pharmacy could read AND modify another pharmacy's
    supplier via GET/PUT /suppliers/{id}. There is no database-level
    tenant isolation (no row-level security) backing this up — every
    query is on its own, which is exactly why one shared, safe-by-default
    helper exists now instead of leaving each router to remember.

    Returns 404 (never 403) when the row exists but belongs to a
    different pharmacy — indistinguishable from "doesn't exist" from the
    caller's side, so this can't be used to enumerate valid IDs in other
    tenants. A malformed (non-UUID) id is also a 404, not a 500.

    design-guard.sh Rule 13 flags a raw `select(Model).where(Model.id ==`
    in a router that doesn't also mention `pharmacy_id` on the same
    statement or come from get_owned_or_404 — use this helper instead of
    hand-writing the check every time.
    """
    if isinstance(record_id, str):
        try:
            record_id = uuid.UUID(record_id)
        except ValueError:
            raise HTTPException(status_code=404, detail=not_found_detail)
    conditions = [model.id == record_id, model.pharmacy_id == pharmacy_id]
    if extra_conditions:
        conditions.extend(extra_conditions)
    result = await db.execute(select(model).where(*conditions))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=not_found_detail)
    return row


async def resolve_store_override(
    current_user: User, requested_pharmacy_id: Optional[str], db: AsyncSession,
) -> uuid.UUID:
    """The HQ-buyer store picker (docs/26_MULTI_CHAIN_SCOPE.md Section 3
    #3) needs read endpoints like GET /suppliers and GET /products to
    list the TARGET store's data, not the caller's currently active
    store — otherwise the picker shows the wrong store's suppliers and
    medicines. Returns the caller's own pharmacy_id unchanged when
    requested_pharmacy_id is blank or matches it; otherwise requires a
    real user_store_roles grant there (403, never trusts the caller-
    supplied id alone). Read-only gate — the actual purchases:create
    check for the WRITE happens separately in routers/purchases.py."""
    from models.users import UserStoreRole as UserStoreRoleORM  # local import avoids a circular import at module load

    if not requested_pharmacy_id or requested_pharmacy_id == current_user.pharmacy_id:
        return uuid.UUID(current_user.pharmacy_id)

    target_pharmacy_id = uuid.UUID(requested_pharmacy_id)
    grant_result = await db.execute(
        select(UserStoreRoleORM).where(
            UserStoreRoleORM.user_id == uuid.UUID(current_user.id),
            UserStoreRoleORM.pharmacy_id == target_pharmacy_id))
    if not grant_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You don't have access to that store")
    return target_pharmacy_id


async def resolve_store_override_for_write(
    current_user: User, requested_pharmacy_id: Optional[str], required_permission: str, db: AsyncSession,
) -> uuid.UUID:
    """Same idea as resolve_store_override, but for a WRITE the HQ-buyer
    picker makes for another store (creating a purchase, or a supplier
    needed to create one — docs/26_MULTI_CHAIN_SCOPE.md Section 3 #3):
    requires the caller's role AT THE TARGET STORE to actually hold
    required_permission (e.g. "purchases:create"), not just any grant
    there. When requested_pharmacy_id is blank or matches the caller's
    own store, this still checks required_permission against the
    caller's OWN current role — never a silent bypass for the common
    case (a real regression caught before it shipped: an earlier draft
    of this helper returned the caller's own pharmacy_id with no
    permission check at all when there was no override)."""
    from models.users import Role as RoleORM, UserStoreRole as UserStoreRoleORM  # local import avoids a circular import

    if not requested_pharmacy_id or requested_pharmacy_id == current_user.pharmacy_id:
        module, _, action = required_permission.partition(":")
        if not await has_permission(current_user, required_permission, db):
            raise HTTPException(
                status_code=403,
                detail=f"Your role does not have permission to {action} {module}")
        return uuid.UUID(current_user.pharmacy_id)

    target_pharmacy_id = uuid.UUID(requested_pharmacy_id)
    grant_result = await db.execute(
        select(UserStoreRoleORM).where(
            UserStoreRoleORM.user_id == uuid.UUID(current_user.id),
            UserStoreRoleORM.pharmacy_id == target_pharmacy_id))
    grant = grant_result.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=403, detail="You don't have access to that store")

    role_result = await db.execute(select(RoleORM).where(RoleORM.id == grant.role_id))
    role = role_result.scalar_one_or_none()
    module, _, action = required_permission.partition(":")
    allowed = False
    if role:
        perms = role.permissions
        if isinstance(perms, list):
            allowed = "*" in perms or required_permission in perms
        elif isinstance(perms, dict):
            allowed = bool(perms.get("*")) or bool(perms.get(module, {}).get(action, False))
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Your role at that store does not have permission to {action} {module}")
    return target_pharmacy_id


async def resolve_chain_scope_pids(current_user: User, scope: str, db: AsyncSession) -> list[uuid.UUID]:
    """The canonical way to turn a `?scope=store|chain` toggle (Dashboard,
    GST report, Purchases analytics — docs/26_MULTI_CHAIN_SCOPE.md Steps 4
    and 6b) into the list of pharmacy_ids a query should sum across.

    "store" (default) = just the caller's own pharmacy, unchanged behavior.
    "chain" = every pharmacy in the caller's chain the caller actually
    holds a real user_store_roles grant at.

    Fixed Sep 28, 2026 (docs/15_ROADMAP.md RULE MISSES LOG): the original
    version of this logic (duplicated inline in reports.py) summed every
    pharmacy sharing the caller's chain_id, full stop — it never checked
    user_store_roles. That meant a user whose home store merely happened
    to sit in a multi-store chain could pull every other branch's
    revenue/GST/purchase totals under scope=chain, even with zero grant
    at those branches — the exact class of bug resolve_store_override /
    resolve_store_override_for_write above exist to prevent for WRITEs,
    never applied to this read-rollup path. This version intersects chain
    membership with the caller's own real grants, so "All Stores" means
    "all stores I actually have access to," never "every store in the
    company." The caller's own home store is always included even if its
    own user_store_roles row is somehow missing (pre-dates the Step 1
    backfill) — this can only ever narrow the chain-membership list, never
    grant access beyond it.
    """
    from models.pharmacy import Pharmacy as PharmacyORM  # local import avoids a circular import at module load
    from models.users import UserStoreRole as UserStoreRoleORM

    own_pid = uuid.UUID(current_user.pharmacy_id)
    if scope != "chain":
        return [own_pid]

    pharmacy = (await db.execute(select(PharmacyORM).where(PharmacyORM.id == own_pid))).scalar_one()
    if pharmacy.chain_id is None:
        return [own_pid]

    chain_pids_result = await db.execute(
        select(PharmacyORM.id).where(PharmacyORM.chain_id == pharmacy.chain_id))
    chain_pids = set(chain_pids_result.scalars().all())

    granted_result = await db.execute(
        select(UserStoreRoleORM.pharmacy_id).where(
            UserStoreRoleORM.user_id == uuid.UUID(current_user.id),
            UserStoreRoleORM.pharmacy_id.in_(chain_pids)))
    granted_pids = set(granted_result.scalars().all())
    granted_pids.add(own_pid)

    return sorted(granted_pids, key=str)


def flatten_permissions(perms, is_admin: bool = False) -> list[str]:
    """A role's stored permissions as a flat list of "module:action" ids — ["*"] for an admin or a
    wildcard role. Sent to the frontend so buttons follow the real Roles & Permissions ticks instead
    of guessing from the role's name."""
    if is_admin:
        return ["*"]
    if isinstance(perms, list):
        return ["*"] if "*" in perms else sorted(perms)
    if isinstance(perms, dict):
        if perms.get("*"):
            return ["*"]
        return sorted(f"{module}:{action}" for module, actions in perms.items()
                      if isinstance(actions, dict) for action, granted in actions.items() if granted)
    return []


async def has_permission(user: User, permission: str, db: AsyncSession) -> bool:
    """Check if a user's role has the given permission (e.g. 'billing:create').
    An admin (users.is_admin) has every permission."""
    if user.is_admin:
        return True
    result = await db.execute(
        select(RoleORM).where(RoleORM.id == uuid.UUID(user.role_id))
    )
    role = result.scalar_one_or_none()
    if not role:
        return False
    perms = role.permissions
    if isinstance(perms, list):
        return "*" in perms or permission in perms
    if isinstance(perms, dict):
        if perms.get("*"):
            return True
        module, _, action = permission.partition(":")
        return bool(perms.get(module, {}).get(action, False))
    return False


async def require_admin_or_super(user: User, db: AsyncSession, detail: str = "Admin access required") -> None:
    """Same gate as `if current_user.role != "admin": raise 403`, but also
    honors a custom role granted the "*" wildcard permission — shown in the
    UI as "Super Admin" (RolesTab.jsx's `is_super_admin` badge). Found Sep
    13, 2026 (Settings product-review): every admin-only endpoint checked
    the literal role name "admin", so a custom role given every permission
    still couldn't manage users/roles/settings/batches — the UI implied
    parity with Admin that the backend never granted. Raises the same 403
    the literal check used to, so callers don't need to change their error
    handling.
    """
    if user.is_admin or user.role == "admin":
        return
    if await has_permission(user, "*", db):
        return
    raise HTTPException(status_code=403, detail=detail)
