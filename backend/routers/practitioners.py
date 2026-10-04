"""Doctors as their own records (docs/31_CORE_DOCTOR_SCOPE.md) — Settings → Organisation → Doctors.

A doctor is owned by the hospital and mapped to the clinics where they practise (with a consultation fee per
clinic). Doctors are NOT logins: a login can optionally be linked. Every lookup goes through the caller's real
store grants (services/practitioners.py)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.practitioners import Practitioner, PractitionerClinic
from models.users import AuditLog, User as UserORM
from routers.auth_helpers import User, get_current_user, has_permission
from services.workspace import caller_workspace
from services.practitioners import Scope, get_visible_or_404, practitioner_scope, shape_many, visible_clause

router = APIRouter(prefix="/api", tags=["practitioners"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str, entity_id: uuid.UUID, new_values: dict,
    db: AsyncSession, old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    db.add(AuditLog(pharmacy_id=pharmacy_id, user_id=user_id, action=action, entity_type="practitioner",
                    entity_id=entity_id, new_values=new_values, old_values=old_values, ip_address=ip_address))


async def _require_doctors_permission(current_user: User, permission: str, db: AsyncSession) -> None:
    if not await has_permission(current_user, permission, db):
        raise HTTPException(status_code=403, detail=f"Your role does not have the '{permission}' permission")


class ClinicLink(BaseModel):
    clinic_id: uuid.UUID
    consultation_fee_paise: Optional[int] = Field(default=None, ge=0)
    is_active: bool = True


class PractitionerBase(BaseModel):
    specialty: Optional[str] = Field(default=None, max_length=100)
    qualification: Optional[str] = Field(default=None, max_length=200)
    registration_no: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=10)
    email: Optional[str] = Field(default=None, max_length=200)
    is_external: bool = False
    hospital: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    clinics: Optional[list[ClinicLink]] = None

    @field_validator("specialty", "qualification", "registration_no", "phone", "email", "hospital", "notes")
    @classmethod
    def _blank_is_none(cls, v):
        v = v.strip() if isinstance(v, str) else v
        return v or None

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v):
        if v is not None and "@" not in v:
            raise ValueError("Enter a valid email address")
        return v


class PractitionerCreate(PractitionerBase):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v):
        if not v.strip():
            raise ValueError("Name is required")
        return v.strip()


class PractitionerUpdate(PractitionerBase):
    name: Optional[str] = Field(default=None, max_length=200)
    is_active: Optional[bool] = None


async def _check_clinics(db: AsyncSession, clinics: list[ClinicLink], scope: Scope) -> None:
    for c in clinics:
        if c.clinic_id not in scope.clinic_ids:
            raise HTTPException(status_code=403, detail="You don't have access to one of those clinics")
    if len({c.clinic_id for c in clinics}) != len(clinics):
        raise HTTPException(status_code=422, detail="A clinic is listed twice")


async def _check_login(db: AsyncSession, user_id: uuid.UUID, scope: Scope,
                       this_practitioner: Optional[uuid.UUID]) -> None:
    user = (await db.execute(select(UserORM).where(
        UserORM.id == user_id, UserORM.chain_id == scope.chain_id,
        UserORM.is_active.is_(True)))).scalar_one_or_none()  # tenant-safe: workspace-scoped login lookup
    if not user:
        raise HTTPException(status_code=404, detail="That login was not found")
    other = (await db.execute(select(Practitioner).where(
        Practitioner.user_id == user_id, Practitioner.deleted_at.is_(None),
        *visible_clause(scope)))).scalar_one_or_none()
    if other and other.id != this_practitioner:
        raise HTTPException(status_code=409, detail=f"That login is already linked to {other.name}")


async def _apply_clinics(db: AsyncSession, p: Practitioner, clinics: list[ClinicLink], scope: Scope) -> None:
    """Make the caller's visible mappings match `clinics`. Mappings at clinics the caller cannot open
    are never touched; removed ones are soft-deleted, a re-added one is revived."""
    existing = (await db.execute(select(PractitionerClinic).where(
        PractitionerClinic.practitioner_id == p.id,
        PractitionerClinic.clinic_id.in_(scope.clinic_ids)))).scalars().all()
    by_clinic = {e.clinic_id: e for e in existing}
    wanted = {c.clinic_id: c for c in clinics}
    for clinic_id, link in by_clinic.items():
        if clinic_id not in wanted and link.deleted_at is None:
            link.deleted_at = datetime.now(timezone.utc)
            link.is_active = False
    for clinic_id, c in wanted.items():
        link = by_clinic.get(clinic_id)
        if link is None:
            db.add(PractitionerClinic(practitioner_id=p.id, clinic_id=clinic_id,
                                      consultation_fee_paise=c.consultation_fee_paise, is_active=c.is_active))
        else:
            link.deleted_at = None
            link.consultation_fee_paise = c.consultation_fee_paise
            link.is_active = c.is_active


@router.get("/practitioners")
async def list_practitioners(
    include_inactive: bool = False, clinic_id: Optional[uuid.UUID] = Query(None),
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    await _require_doctors_permission(current_user, "doctors:view", db)
    scope = await practitioner_scope(db, current_user)
    if clinic_id is not None and clinic_id not in scope.clinic_ids:
        raise HTTPException(status_code=403, detail="You don't have access to that clinic")
    if clinic_id is not None:  # one clinic's doctor list: only doctors actually mapped to it
        query = select(Practitioner).where(Practitioner.deleted_at.is_(None), Practitioner.id.in_(
            select(PractitionerClinic.practitioner_id).where(
                PractitionerClinic.clinic_id == clinic_id, PractitionerClinic.is_active.is_(True),
                PractitionerClinic.deleted_at.is_(None))))
    else:
        query = select(Practitioner).where(*visible_clause(scope))
    if not include_inactive:
        query = query.where(Practitioner.is_active.is_(True))
    items = (await db.execute(query.order_by(Practitioner.name))).scalars().all()
    return await shape_many(db, list(items), scope)


@router.get("/practitioners/linkable-users")
async def linkable_users(current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Active logins in the caller's workspace not yet linked to a doctor — for the 'Linked login' picker."""
    await _require_doctors_permission(current_user, "doctors:edit", db)
    taken = select(Practitioner.user_id).where(
        Practitioner.user_id.is_not(None), Practitioner.deleted_at.is_(None))
    users = (await db.execute(select(UserORM).where(
        UserORM.chain_id == await caller_workspace(db, current_user), UserORM.is_active.is_(True),
        UserORM.id.not_in(taken))
        .order_by(UserORM.name))).scalars().all()
    return [{"id": str(u.id), "name": u.name, "email": u.email} for u in users]


@router.post("/practitioners")
async def create_practitioner(data: PractitionerCreate, request: Request,
                              current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_doctors_permission(current_user, "doctors:edit", db)
    home = uuid.UUID(current_user.pharmacy_id)
    scope = await practitioner_scope(db, current_user)
    active = uuid.UUID(current_user.clinic_id) if current_user.clinic_id else None
    clinics = data.clinics if data.clinics is not None else ([ClinicLink(clinic_id=active)] if active else [])
    await _check_clinics(db, clinics, scope)
    if data.user_id:
        await _check_login(db, data.user_id, scope, None)
    chain_id = scope.chain_id
    fields = data.model_dump(exclude={"clinics"})
    p = Practitioner(pharmacy_id=home, chain_id=chain_id, **fields)
    db.add(p)
    await db.flush()
    await _apply_clinics(db, p, clinics, scope)
    await db.flush()
    await _record_audit(home, uuid.UUID(current_user.id), "create", p.id,
                        {**{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in fields.items()},
                         "clinics": [str(c.clinic_id) for c in clinics]}, db, ip_address=_client_ip(request))
    return (await shape_many(db, [p], scope))[0]


@router.get("/practitioners/{practitioner_id}")
async def get_practitioner(practitioner_id: str, current_user: User = Depends(get_current_user),
                           db: AsyncSession = DbSession):
    await _require_doctors_permission(current_user, "doctors:view", db)
    scope = await practitioner_scope(db, current_user)
    p = await get_visible_or_404(db, practitioner_id, scope)
    return (await shape_many(db, [p], scope))[0]


@router.put("/practitioners/{practitioner_id}")
async def update_practitioner(practitioner_id: str, data: PractitionerUpdate, request: Request,
                              current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_doctors_permission(current_user, "doctors:edit", db)
    scope = await practitioner_scope(db, current_user)
    p = await get_visible_or_404(db, practitioner_id, scope)
    sent = data.model_fields_set
    changes = {k: getattr(data, k) for k in sent if k not in ("clinics",)}
    if "name" in changes and not (changes["name"] or "").strip():
        raise HTTPException(status_code=422, detail="Name is required")
    if "is_active" in changes and changes["is_active"] is None:
        changes.pop("is_active")
    if "is_external" in changes and changes["is_external"] is None:
        changes.pop("is_external")
    if changes.get("user_id"):
        await _check_login(db, changes["user_id"], scope, p.id)
    if data.clinics is not None:
        await _check_clinics(db, data.clinics, scope)
    old = {k: (str(getattr(p, k)) if isinstance(getattr(p, k), uuid.UUID) else getattr(p, k)) for k in changes}
    for k, v in changes.items():
        setattr(p, k, v.strip() if k == "name" and isinstance(v, str) else v)
    if data.clinics is not None:
        await _apply_clinics(db, p, data.clinics, scope)
    await db.flush()
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "update", p.id,
        {**{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in changes.items()},
         **({"clinics": [str(c.clinic_id) for c in data.clinics]} if data.clinics is not None else {})},
        db, old_values=old or None, ip_address=_client_ip(request))
    return (await shape_many(db, [p], scope))[0]


@router.delete("/practitioners/{practitioner_id}")
async def delete_practitioner(practitioner_id: str, request: Request,
                              current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Soft delete: the record, its clinic mappings and the login link are released, never erased."""
    await _require_doctors_permission(current_user, "doctors:edit", db)
    scope = await practitioner_scope(db, current_user)
    p = await get_visible_or_404(db, practitioner_id, scope)
    now = datetime.now(timezone.utc)
    links = (await db.execute(select(PractitionerClinic).where(
        PractitionerClinic.practitioner_id == p.id, PractitionerClinic.clinic_id.in_(scope.clinic_ids),
        PractitionerClinic.deleted_at.is_(None)))).scalars().all()
    for link in links:
        link.deleted_at, link.is_active = now, False
    old = {"name": p.name, "is_active": p.is_active, "user_id": str(p.user_id) if p.user_id else None}
    p.deleted_at, p.is_active, p.user_id = now, False, None
    await db.flush()
    await _record_audit(uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "delete", p.id,
                        {"deleted": True}, db, old_values=old, ip_address=_client_ip(request))
    return {"message": "Doctor removed"}
