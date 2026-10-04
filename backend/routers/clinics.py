"""Clinics (EMR places) — Settings → Organisation → Clinics (docs/32_CLINICS_SCOPE.md).

Separate from pharmacies. Visible to everyone in the same hospital who holds `clinics:view`; creating and
editing follow the `clinics:create` / `clinics:edit` ticks of the login's role (administrators always).
A clinic is deactivated, never deleted."""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.clinics import Clinic
from models.users import AuditLog, User as UserORM, UserClinicAccess
from routers.auth_helpers import User, get_current_user, has_permission
from services.clinics import get_clinic_or_404, list_clinics, name_taken, shape
from services.workspace import caller_workspace

router = APIRouter(prefix="/api", tags=["clinics"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str, entity_id: uuid.UUID, new_values: dict,
    db: AsyncSession, old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    db.add(AuditLog(pharmacy_id=pharmacy_id, user_id=user_id, action=action, entity_type="clinic",
                    entity_id=entity_id, new_values=new_values, old_values=old_values, ip_address=ip_address))


async def _require_clinics_permission(current_user: User, permission: str, db: AsyncSession) -> None:
    if not await has_permission(current_user, permission, db):
        raise HTTPException(status_code=403, detail=f"Your role does not have the '{permission}' permission")


class ClinicBase(BaseModel):
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=200)
    registration_no: Optional[str] = Field(default=None, max_length=100)

    @field_validator("address", "city", "state", "pincode", "phone", "email", "registration_no")
    @classmethod
    def _blank_is_none(cls, v):
        v = v.strip() if isinstance(v, str) else v
        return v or None

    @field_validator("pincode")
    @classmethod
    def _six_digits(cls, v):
        if v is not None and not re.fullmatch(r"\d{6}", v):
            raise ValueError("Pincode must be 6 digits")
        return v

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v):
        if v is not None and "@" not in v:
            raise ValueError("Enter a valid email address")
        return v


class ClinicCreate(ClinicBase):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Clinic name is required")
        return v


class ClinicUpdate(ClinicBase):
    name: Optional[str] = Field(default=None, max_length=200)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Clinic name cannot be blank")
        return v


@router.get("/clinics")
async def list_all_clinics(include_inactive: bool = Query(False), current_user: User = Depends(get_current_user),
                           db: AsyncSession = DbSession):
    await _require_clinics_permission(current_user, "clinics:view", db)
    rows = await list_clinics(db, uuid.UUID(current_user.pharmacy_id), include_inactive)
    return [shape(c) for c in rows]


@router.post("/clinics")
async def create_clinic(body: ClinicCreate, request: Request, current_user: User = Depends(get_current_user),
                        db: AsyncSession = DbSession):
    await _require_clinics_permission(current_user, "clinics:create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    if await name_taken(db, pharmacy_id, body.name):
        raise HTTPException(status_code=409, detail=f"A clinic named '{body.name}' already exists")
    clinic = Clinic(chain_id=await caller_workspace(db, current_user), **body.model_dump())
    db.add(clinic)
    await db.flush()
    # The creator can open the clinic they just made (with the role they already hold), and it becomes
    # their active clinic if they had none.
    db.add(UserClinicAccess(user_id=uuid.UUID(current_user.id), clinic_id=clinic.id,
                            role_id=uuid.UUID(current_user.role_id)))
    if current_user.clinic_id is None:
        await db.execute(update(UserORM).where(UserORM.id == uuid.UUID(current_user.id)).values(clinic_id=clinic.id))
    await db.flush()
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "create", clinic.id,
                        {"name": clinic.name, "city": clinic.city}, db, ip_address=_client_ip(request))
    await db.flush()
    return shape(clinic)


@router.get("/clinics/{clinic_id}")
async def get_clinic(clinic_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_clinics_permission(current_user, "clinics:view", db)
    return shape(await get_clinic_or_404(db, clinic_id, uuid.UUID(current_user.pharmacy_id)))


@router.put("/clinics/{clinic_id}")
async def update_clinic(clinic_id: str, body: ClinicUpdate, request: Request,
                        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_clinics_permission(current_user, "clinics:edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    clinic = await get_clinic_or_404(db, clinic_id, pharmacy_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        changes.pop("name")
    if "is_active" in changes and changes["is_active"] is None:
        changes.pop("is_active")
    if "name" in changes and await name_taken(db, pharmacy_id, changes["name"], except_id=clinic.id):
        raise HTTPException(status_code=409, detail=f"A clinic named '{changes['name']}' already exists")
    old = {k: getattr(clinic, k) for k in changes}
    for key, value in changes.items():
        setattr(clinic, key, value)
    await db.flush()
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "update", clinic.id, changes, db,
                        old_values=old, ip_address=_client_ip(request))
    await db.flush()
    return shape(clinic)
