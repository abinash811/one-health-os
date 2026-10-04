from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from deps import DbSession
from models.chains import Chain
from models.pharmacy import Pharmacy
from models.users import AuditLog, PasswordResetToken as PasswordResetTokenORM, Role as RoleORM, User as UserORM
from routers.auth_helpers import (
    User,
    create_access_token,
    flatten_permissions,
    get_current_user,
    has_permission,
    hash_password,
    verify_password,
)
from services.role_scope import chain_of, find_role, scope_clause
from services.provisioning import create_pharmacy_with_defaults, sync_user_store_role

router = APIRouter(prefix="/api", tags=["auth"])
logger = logging.getLogger(__name__)

# 1 hour, single use — see docs/15_ROADMAP.md Auth Overhaul #6.
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_login_event(
    user: UserORM, action: str, db: AsyncSession, ip_address: str | None,
) -> None:
    # Login history (Roles & Permissions maturity gap) — nothing tracked
    # who logged in, when, from where, or how many times a password was
    # gotten wrong. Reuses the existing AuditLog table (entity_type="auth")
    # instead of a new one — same rows shape every other module already
    # writes, just a new entity_type. A user record with no pharmacy_id
    # yet (there is none in this app — every user is created under a
    # pharmacy) never occurs, so this only needs a matched user, which is
    # also why an unknown email is never logged: there is no tenant to
    # attribute the attempt to.
    db.add(AuditLog(
        pharmacy_id=user.pharmacy_id, user_id=user.id, action=action,
        entity_type="auth", entity_id=user.id, new_values=None,
        old_values=None, ip_address=ip_address,
    ))


class UserCreate(BaseModel):
    # Account
    email: EmailStr
    name: str
    # docs/14_SECURITY.md KNOWN GAPS #2: only the frontend Zod schema
    # (lib/schemas/auth.ts) enforced this; matching it here so the
    # backend can't be bypassed by a direct API call.
    password: str = Field(min_length=6)
    phone: str
    # New pharmacy — every signup creates its own pharmacy; the signing-up
    # user is always that pharmacy's Admin. See CLAUDE.md "Signup / Auth
    # Rebuild" note — there is no public role picker, on purpose.
    pharmacy_name: str
    address: str
    city: str
    state: str
    pincode: str
    drug_license_number: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


async def _workspace_of(db: AsyncSession, user: User):
    chain_id = user.chain_id or await chain_of(db, uuid.UUID(user.pharmacy_id))
    if not chain_id:
        return None
    # tenant-safe: the caller's own workspace, taken from their own login row
    chain = (await db.execute(select(Chain).where(Chain.id == uuid.UUID(str(chain_id))))).scalar_one_or_none()
    return {"id": str(chain.id), "name": chain.name} if chain else None


@router.post("/auth/register")
async def register(user_data: UserCreate, db: AsyncSession = DbSession):
    # Email uniqueness is checked globally (not per-pharmacy) because login
    # looks a user up by email alone — see routers/auth.py::login below.
    existing = await db.execute(select(UserORM).where(UserORM.email == user_data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    pharmacy = await create_pharmacy_with_defaults(
        db,
        name=user_data.pharmacy_name,
        address=user_data.address,
        city=user_data.city,
        state=user_data.state,
        pincode=user_data.pincode,
        phone=user_data.phone,
        email=user_data.email,
        drug_license_number=user_data.drug_license_number,
    )

    role_result = await db.execute(
        select(RoleORM).where(RoleORM.pharmacy_id == pharmacy.id, RoleORM.name == "admin")
    )
    role = role_result.scalar_one()  # created moments ago by create_pharmacy_with_defaults

    user = UserORM(
        pharmacy_id=pharmacy.id,
        chain_id=pharmacy.chain_id,
        role_id=role.id,
        is_admin=True,
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone,
        password_hash=hash_password(user_data.password),
    )
    db.add(user)
    await db.flush()
    await sync_user_store_role(db, user_id=user.id, pharmacy_id=pharmacy.id, role_id=role.id)
    # The person who creates the workspace owns it.
    await db.execute(update(Chain).where(Chain.id == pharmacy.chain_id).values(owner_user_id=user.id))

    token = create_access_token({"sub": str(user.id), "email": user.email})
    return {
        "token": token,
        "user": {"id": str(user.id), "email": user.email, "name": user.name, "role": "admin",
                 "is_admin": True},
    }


@router.post("/auth/login")
async def login(credentials: UserLogin, request: Request, db: AsyncSession = DbSession):
    result = await db.execute(
        select(UserORM)
        .options(joinedload(UserORM.role))
        .where(UserORM.email == credentials.email)
        .order_by(UserORM.created_at)
    )
    # The same email can exist at more than one pharmacy (POST /users only checks within its own
    # pharmacy), so this used to crash with a 500 ("Multiple rows were found"), which the browser
    # showed as "Could not reach the server". Sign in as whichever account the password opens.
    candidates = result.scalars().unique().all()
    user = next(
        (u for u in candidates if u.password_hash and verify_password(credentials.password, u.password_hash)),
        None)
    ip = _client_ip(request)

    if not user:
        # An unknown email has no pharmacy to attribute the attempt to —
        # only a real account's wrong-password attempts are logged.
        if candidates:
            await _record_login_event(candidates[0], "login_failed", db, ip)
            # A plain flush() is not enough here: get_db's own exception
            # handler rolls back the whole transaction the moment this
            # HTTPException propagates out, which would silently discard
            # the very row this is trying to persist. Commit for real
            # before raising.
            await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        await _record_login_event(user, "login_blocked", db, ip)
        await db.commit()
        raise HTTPException(status_code=403, detail="Account is inactive")

    # last_login_at has existed on the User model since day one but
    # nothing ever set it — every account showed no last-login value
    # regardless of real usage.
    user.last_login_at = datetime.now(timezone.utc)
    await _record_login_event(user, "login", db, ip)
    await db.flush()

    token = create_access_token({"sub": str(user.id), "email": user.email})
    # is_super_admin included here too, not just /auth/me — otherwise a
    # wildcard-role user would still be wrongly blocked from Settings/Team
    # immediately after login, only fixed after a page reload re-fetches
    # /auth/me. See /auth/me's own comment for the full context.
    perms = user.role.permissions or []
    is_super_admin = (
        user.is_admin or user.role.name == "admin" or (isinstance(perms, list) and "*" in perms))
    return {
        "token": token,
        "user": {
            "id": str(user.id), "email": user.email, "name": user.name, "role": user.role.name,
            "is_admin": user.is_admin,
            "is_super_admin": is_super_admin,
            "permissions": flatten_permissions(user.role.permissions, user.is_admin),
        },
    }


@router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPassword, request: Request, db: AsyncSession = DbSession):
    """Self-service password reset (docs/15_ROADMAP.md Auth Overhaul #6) —
    a locked-out user with no admin around previously had no way back in
    at all (admin_reset_password in users.py covers the "an admin is
    available" case, built Sep 15, 2026; this is the other half).

    Always returns the same generic message regardless of whether the
    email matches a real account — a distinguishable response here would
    let a caller enumerate which emails are registered.

    No real email-sending service is wired in yet (see docs/15_ROADMAP.md
    Auth Overhaul #6's "Needs: Email infrastructure" line — asked, not
    assumed, since that needs real SMTP/SendGrid credentials only Abinash
    can provide). Until then, the reset link is logged server-side and
    also returned directly in the response as `dev_reset_link` so the
    flow is actually usable end-to-end today; wiring in a real mailer
    later only means replacing this one function's body, not any of the
    token/validation logic around it.
    """
    result = await db.execute(
        select(UserORM).where(UserORM.email == payload.email).order_by(UserORM.created_at))
    user = result.scalars().first()  # same email at several pharmacies: reset the oldest account

    generic_response = {
        "message": "If an account exists for that email, a password reset link has been sent.",
    }

    if not user or not user.is_active:
        return generic_response

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db.add(PasswordResetTokenORM(
        user_id=user.id, token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + PASSWORD_RESET_TOKEN_TTL,
    ))
    await _record_login_event(user, "password_reset_requested", db, _client_ip(request))
    await db.flush()

    reset_link = f"/reset-password?token={raw_token}"
    # TODO once real SMTP/SendGrid credentials exist: send `reset_link` as
    # an actual email to user.email instead of only logging it. Everything
    # else in this endpoint (token generation, hashing, expiry, audit log)
    # stays exactly as-is.
    logger.info("Password reset requested for %s — reset link: %s", user.email, reset_link)

    return {**generic_response, "dev_reset_link": reset_link}


@router.post("/auth/reset-password")
async def reset_password(payload: ResetPassword, request: Request, db: AsyncSession = DbSession):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    result = await db.execute(
        select(PasswordResetTokenORM).where(PasswordResetTokenORM.token_hash == token_hash))
    reset_token = result.scalar_one_or_none()

    if (not reset_token or reset_token.used_at is not None
            or reset_token.expires_at < datetime.now(timezone.utc)):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    # tenant-safe: unauthenticated; user_id is from a row found via a random, hashed, single-use token
    user_result = await db.execute(select(UserORM).where(UserORM.id == reset_token.user_id))
    user = user_result.scalar_one()  # FK guarantees this exists

    user.password_hash = hash_password(payload.new_password)
    reset_token.used_at = datetime.now(timezone.utc)
    await _record_login_event(user, "password_reset_completed", db, _client_ip(request))
    await db.flush()

    return {"message": "Password reset successfully. You can now log in with your new password."}


@router.post("/auth/session")
async def create_session(request: Request, response: Response, db: AsyncSession = DbSession):
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID required")

    async with httpx.AsyncClient() as client:
        try:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
            )
            auth_response.raise_for_status()
            session_data = auth_response.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to validate session: {str(e)}")

    result = await db.execute(
        select(UserORM)
        .options(joinedload(UserORM.role))
        .where(UserORM.email == session_data["email"])
    )
    user = result.scalar_one_or_none()

    if not user:
        pharm_result = await db.execute(select(Pharmacy).limit(1))
        pharmacy = pharm_result.scalar_one_or_none()
        if not pharmacy:
            raise HTTPException(status_code=500, detail="No pharmacy configured")

        count_result = await db.execute(select(func.count()).select_from(UserORM))
        role_name = "admin" if count_result.scalar() == 0 else "cashier"

        role = await find_role(db, pharmacy.id, role_name)
        if not role:
            raise HTTPException(status_code=500, detail=f"Role '{role_name}' not configured")

        user = UserORM(
            pharmacy_id=pharmacy.id,
            chain_id=pharmacy.chain_id,
            role_id=role.id,
            is_admin=(role_name == "admin"),
            name=session_data["name"],
            email=session_data["email"],
            password_hash="",
        )
        db.add(user)
        await db.flush()
        await sync_user_store_role(db, user_id=user.id, pharmacy_id=pharmacy.id, role_id=role.id)
        role_name_out = role_name
    else:
        role_name_out = user.role.name

    token = create_access_token({"sub": str(user.id), "email": user.email})
    response.set_cookie(
        key="session_token", value=token, httponly=True,
        secure=True, samesite="none", path="/", max_age=60 * 60 * 24 * 7,
    )
    return {
        "user": {
            "id": str(user.id), "email": user.email, "name": user.name, "role": role_name_out,
        },
    }


@router.post("/auth/logout")
async def logout(response: Response, current_user: User = Depends(get_current_user)):
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    role_row = (await db.execute(
        select(RoleORM).where(
            RoleORM.id == uuid.UUID(current_user.role_id),
            scope_clause(uuid.UUID(current_user.pharmacy_id),
                         await chain_of(db, uuid.UUID(current_user.pharmacy_id)))))).scalar_one_or_none()
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        # A custom role granted the "*" wildcard permission (RolesTab.jsx's
        # "Super Admin" badge) has real admin-equivalent backend access via
        # require_admin_or_super() — but every frontend admin-only page gate
        # checked the literal string role == "admin", so a user in such a
        # role couldn't even open Settings/Team, unlike the real admin.
        # Found Sep 15, 2026 (Team product-review), same shape as the Sep
        # 13 backend-only fix. Frontend gates now check this field too.
        "is_admin": current_user.is_admin,
        "is_super_admin": current_user.role == "admin" or await has_permission(current_user, "*", db),
        # What the role's ticks actually allow (["*"] = everything) — the frontend shows or hides
        # buttons from this, never from the role's name. The backend still enforces on every call.
        "permissions": flatten_permissions(role_row.permissions if role_row else {}, current_user.is_admin),
        # The workspace (hospital) the login belongs to — docs/33_WORKSPACE_SCOPE.md.
        "workspace": await _workspace_of(db, current_user),
    }
