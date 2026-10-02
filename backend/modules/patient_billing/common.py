"""Permission gate + audit helper for the Patient Billing routers."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.users import AuditLog
from routers.auth_helpers import User, has_permission


async def _require_billing_permission(current_user: User, permission: str, db: AsyncSession) -> None:
    """`permission` is a full id from constants.ALL_PERMISSIONS, e.g. 'patient_billing:collect'."""
    if not await has_permission(current_user, permission, db):
        raise HTTPException(
            status_code=403, detail=f"Your role does not have the '{permission}' permission")


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        old_values=old_values, new_values=new_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
