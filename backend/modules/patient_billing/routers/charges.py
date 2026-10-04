"""Patient Billing — charges. This is what other modules post to (EMR, lab, IPD, front desk)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from modules.patient_billing import service
from modules.patient_billing.common import _client_ip, _record_audit, _require_billing_permission
from modules.patient_billing.constants import MAX_AMOUNT_PAISE, SRC_MANUAL
from modules.patient_billing.models import PbChargeItem
from modules.patient_billing.responses import charge_dict
from routers.auth_helpers import User, get_current_user
from services.clinics import active_clinic_id, get_clinic_owned_or_404

router = APIRouter(prefix="/api/patient-billing", tags=["patient-billing-charges"])


class ChargeCreate(BaseModel):
    patient_id: uuid.UUID
    patient_name: str = Field(min_length=1, max_length=200)
    patient_uhid: Optional[str] = Field(None, max_length=30)
    source_module: str = SRC_MANUAL
    source_ref: Optional[str] = Field(None, max_length=100)
    encounter_ref: Optional[str] = Field(None, max_length=100)
    encounter_type: Optional[str] = Field(None, max_length=20)
    description: str = Field(min_length=1, max_length=300)
    quantity: int = 1
    unit_price_paise: int = Field(ge=1, le=MAX_AMOUNT_PAISE)
    idempotency_key: Optional[str] = Field(None, max_length=150)


class VoidBody(BaseModel):
    reason: str = Field(min_length=1)


@router.post("/charges")
async def post_charge(data: ChargeCreate, request: Request,
                      current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Adds a charge to a patient's account. Retrying with the same `idempotency_key` is safe."""
    await _require_billing_permission(current_user, "patient_billing:charge", db)
    clinic_id = active_clinic_id(current_user)
    charge, created = await service.post_charge(
        db, clinic_id=clinic_id, user_id=uuid.UUID(current_user.id), **data.model_dump())
    if created:
        await _record_audit(
            clinic_id, uuid.UUID(current_user.id), "create", "pb_charge_item", charge.id,
            {"description": charge.description, "total_paise": charge.total_paise,
             "source_module": charge.source_module, "patient_id": str(charge.patient_id)},
            db, ip_address=_client_ip(request))
    return charge_dict(charge)


@router.post("/charges/{charge_id}/void")
async def void_charge(charge_id: uuid.UUID, data: VoidBody, request: Request,
                      current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_billing_permission(current_user, "patient_billing:void", db)
    clinic_id = active_clinic_id(current_user)
    charge = await get_clinic_owned_or_404(
        db, PbChargeItem, charge_id, clinic_id, not_found_detail="Charge not found",
        extra_conditions=[PbChargeItem.deleted_at.is_(None)])
    await db.refresh(charge, with_for_update=True)
    await service.void_charge(db, charge, data.reason)
    await _record_audit(
        clinic_id, uuid.UUID(current_user.id), "void", "pb_charge_item", charge.id,
        {"reason": charge.void_reason, "total_paise": charge.total_paise}, db,
        ip_address=_client_ip(request))
    return charge_dict(charge)
