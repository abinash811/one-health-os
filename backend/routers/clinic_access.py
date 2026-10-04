"""Which clinics a login can open, and which one they are working at (docs/32_CLINICS_SCOPE.md P2).

The clinic twin of the store-access endpoints in users.py: a person's access row carries their role at that
clinic; switching to a clinic makes it the active one and (like switching stores) takes that role. Granting
and revoking are administrator actions, scoped to the caller's workspace."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.clinics import Clinic
from models.users import AuditLog, Role as RoleORM, User as UserORM, UserClinicAccess
from routers.auth_helpers import User, get_current_user, require_admin_or_super
from services.clinics import get_clinic_or_404
from services.role_scope import find_role
from services.workspace import caller_workspace, get_workspace_user_or_404

router = APIRouter(prefix="/api", tags=["clinic-access"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str, entity_id: uuid.UUID, new_values: dict,
    db: AsyncSession, old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    db.add(AuditLog(pharmacy_id=pharmacy_id, user_id=user_id, action=action, entity_type="user",
                    entity_id=entity_id, new_values=new_values, old_values=old_values, ip_address=ip_address))


class SwitchClinic(BaseModel):
    clinic_id: str


class GrantClinicAccess(BaseModel):
    clinic_id: str
    role: str


@router.get("/users/me/clinics")
async def get_my_clinics(current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Clinics this person can open, for the sidebar switcher.
    # permission-exempt: self-service, scoped to the caller's own access rows
    """
    rows = (await db.execute(
        select(UserClinicAccess, Clinic.name, RoleORM.name)
        .join(Clinic, Clinic.id == UserClinicAccess.clinic_id)  # tenant-safe: own rows
        .join(RoleORM, RoleORM.id == UserClinicAccess.role_id)
        .where(UserClinicAccess.user_id == uuid.UUID(current_user.id), Clinic.is_active,
               Clinic.deleted_at.is_(None))
        .order_by(Clinic.name))).all()
    return [{"clinic_id": str(a.clinic_id), "clinic_name": name, "role_name": role_name,
             "is_active": str(a.clinic_id) == current_user.clinic_id} for a, name, role_name in rows]


@router.post("/users/me/switch-clinic")
async def switch_clinic(body: SwitchClinic, request: Request, current_user: User = Depends(get_current_user),
                        db: AsyncSession = DbSession):
    """Makes another clinic this person already has access to their active one (and takes their role there,
    as switching stores does).
    # permission-exempt: self-service, only into a clinic this exact user has a real access row for
    """
    try:
        clinic_id = uuid.UUID(body.clinic_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Clinic not found")
    access = (await db.execute(select(UserClinicAccess).where(
        UserClinicAccess.user_id == uuid.UUID(current_user.id),
        UserClinicAccess.clinic_id == clinic_id))).scalar_one_or_none()
    clinic = (await db.execute(select(Clinic).where(  # tenant-safe: id came from the caller's own access row
        Clinic.id == clinic_id, Clinic.is_active, Clinic.deleted_at.is_(None)))).scalar_one_or_none()
    if not access or not clinic:
        raise HTTPException(status_code=403, detail="You do not have access to that clinic")
    user = (await db.execute(  # tenant-safe: id is the caller's own JWT subject
        select(UserORM).where(UserORM.id == uuid.UUID(current_user.id)))).scalar_one()
    old = user.clinic_id
    user.clinic_id = clinic_id
    user.role_id = access.role_id
    await db.flush()
    await _record_audit(uuid.UUID(current_user.pharmacy_id), user.id, "switch_clinic", user.id,
                        {"clinic_id": str(clinic_id)}, db, old_values={"clinic_id": str(old) if old else None},
                        ip_address=_client_ip(request))
    await db.flush()
    return {"message": "Switched clinic successfully", "clinic_id": str(clinic_id)}


@router.get("/users/{user_id}/clinic-access")
async def get_user_clinic_access(user_id: str, current_user: User = Depends(get_current_user),
                                 db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    target = await get_workspace_user_or_404(db, user_id, await caller_workspace(db, current_user))
    rows = (await db.execute(
        select(UserClinicAccess, Clinic.name, RoleORM.name)
        .join(Clinic, Clinic.id == UserClinicAccess.clinic_id)  # tenant-safe: own rows
        .join(RoleORM, RoleORM.id == UserClinicAccess.role_id)
        .where(UserClinicAccess.user_id == target.id).order_by(Clinic.name))).all()
    return [{"clinic_id": str(a.clinic_id), "clinic_name": name, "role_name": role_name}
            for a, name, role_name in rows]


@router.post("/users/{user_id}/clinic-access")
async def grant_user_clinic_access(user_id: str, body: GrantClinicAccess, request: Request,
                                   current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    target = await get_workspace_user_or_404(db, user_id, await caller_workspace(db, current_user))
    clinic = await get_clinic_or_404(db, body.clinic_id, pharmacy_id)
    role = await find_role(db, pharmacy_id, body.role)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role}' not found")
    existing = (await db.execute(select(UserClinicAccess).where(
        UserClinicAccess.user_id == target.id, UserClinicAccess.clinic_id == clinic.id))).scalar_one_or_none()
    if existing:
        existing.role_id = role.id
    else:
        db.add(UserClinicAccess(user_id=target.id, clinic_id=clinic.id, role_id=role.id))
    if target.clinic_id is None:
        target.clinic_id = clinic.id
    await db.flush()
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "grant_clinic_access", target.id,
                        {"clinic_id": str(clinic.id), "role": body.role}, db, ip_address=_client_ip(request))
    await db.flush()
    return {"message": "Clinic access granted"}


@router.delete("/users/{user_id}/clinic-access/{clinic_id}")
async def revoke_user_clinic_access(user_id: str, clinic_id: str, request: Request,
                                    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    target = await get_workspace_user_or_404(db, user_id, await caller_workspace(db, current_user))
    clinic = await get_clinic_or_404(db, clinic_id, pharmacy_id)
    grants = list((await db.execute(select(UserClinicAccess).where(
        UserClinicAccess.user_id == target.id))).scalars().all())
    grant = next((g for g in grants if g.clinic_id == clinic.id), None)
    if not grant:
        raise HTTPException(status_code=404, detail="No such clinic access grant")
    await db.delete(grant)
    if target.clinic_id == clinic.id:
        rest = [g for g in grants if g.clinic_id != clinic.id]
        target.clinic_id = rest[0].clinic_id if rest else None
    await db.flush()
    await _record_audit(pharmacy_id, uuid.UUID(current_user.id), "revoke_clinic_access", target.id,
                        {"clinic_id": str(clinic.id)}, db, ip_address=_client_ip(request))
    await db.flush()
    return {"message": "Clinic access revoked"}
