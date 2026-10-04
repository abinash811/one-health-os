"""Patient Billing — invoices, payments and the one-step 'collect'."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from modules.patient_billing import service
from modules.patient_billing.common import _client_ip, _record_audit, _require_billing_permission
from modules.patient_billing.constants import (
    COUNTER_BILLING_DESK, INV_CANCELLED, MAX_AMOUNT_PAISE)
from modules.patient_billing.models import PbInvoice, PbPayment
from modules.patient_billing.responses import invoice_dict, payment_dict
from routers.auth_helpers import User, get_current_user, paginate_response
from services.clinics import active_clinic_id, get_clinic_owned_or_404

router = APIRouter(prefix="/api/patient-billing", tags=["patient-billing-invoices"])


class InvoiceCreate(BaseModel):
    patient_id: uuid.UUID
    charge_item_ids: list[uuid.UUID]
    discount_paise: int = Field(0, ge=0, le=MAX_AMOUNT_PAISE)
    counter: str = COUNTER_BILLING_DESK


class PaymentCreate(BaseModel):
    amount_paise: int = Field(ge=1, le=MAX_AMOUNT_PAISE)
    mode: str
    reference: Optional[str] = Field(None, max_length=100)


class CollectBody(BaseModel):
    """Invoice the chosen unbilled charges and take payment in one step (the 'Collect' button)."""
    charge_item_ids: list[uuid.UUID]
    discount_paise: int = Field(0, ge=0, le=MAX_AMOUNT_PAISE)
    amount_paise: Optional[int] = Field(None, ge=1, le=MAX_AMOUNT_PAISE)  # omitted = pay in full
    mode: str
    reference: Optional[str] = Field(None, max_length=100)
    counter: str = COUNTER_BILLING_DESK


class CancelBody(BaseModel):
    reason: str = Field(min_length=1)


async def _locked_invoice(db, invoice_id, clinic_id) -> PbInvoice:
    inv = await get_clinic_owned_or_404(
        db, PbInvoice, invoice_id, clinic_id, not_found_detail="Invoice not found",
        extra_conditions=[PbInvoice.deleted_at.is_(None)])
    await db.refresh(inv, with_for_update=True)  # two simultaneous payments can never overpay
    return inv


@router.post("/invoices")
async def create_invoice(data: InvoiceCreate, request: Request,
                         current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_billing_permission(current_user, "patient_billing:invoice", db)
    clinic_id = active_clinic_id(current_user)
    inv = await service.create_invoice(
        db, clinic_id=clinic_id, user_id=uuid.UUID(current_user.id), patient_id=data.patient_id,
        charge_ids=data.charge_item_ids, discount_paise=data.discount_paise, counter=data.counter)
    await _record_audit(
        clinic_id, uuid.UUID(current_user.id), "create", "pb_invoice", inv.id,
        {"invoice_number": inv.invoice_number, "net_paise": inv.net_paise,
         "discount_paise": inv.discount_paise, "charges": len(inv.lines)}, db,
        ip_address=_client_ip(request))
    return invoice_dict(inv)


@router.get("/invoices")
async def list_invoices(status: Optional[str] = None, patient_id: Optional[uuid.UUID] = None,
                        search: Optional[str] = None, page: int = 1, page_size: int = Query(25, le=100),
                        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_billing_permission(current_user, "patient_billing:view", db)
    q = select(PbInvoice).where(PbInvoice.clinic_id == active_clinic_id(current_user),
                                PbInvoice.deleted_at.is_(None))
    if status:
        q = q.where(PbInvoice.status == status)
    if patient_id:
        q = q.where(PbInvoice.patient_id == patient_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.where(or_(PbInvoice.patient_name.ilike(like), PbInvoice.patient_uhid.ilike(like),
                        PbInvoice.invoice_number.ilike(like)))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(q.order_by(PbInvoice.created_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return paginate_response([invoice_dict(i) for i in rows], page, page_size, total)


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: uuid.UUID, current_user: User = Depends(get_current_user),
                      db: AsyncSession = DbSession):
    await _require_billing_permission(current_user, "patient_billing:view", db)
    clinic_id = active_clinic_id(current_user)
    inv = await get_clinic_owned_or_404(
        db, PbInvoice, invoice_id, clinic_id, not_found_detail="Invoice not found",
        extra_conditions=[PbInvoice.deleted_at.is_(None)])
    pays = (await db.execute(select(PbPayment).where(
        PbPayment.clinic_id == clinic_id, PbPayment.invoice_id == inv.id)
        .order_by(PbPayment.created_at))).scalars().all()
    return {**invoice_dict(inv), "payments": [payment_dict(p, inv.invoice_number) for p in pays]}


@router.post("/invoices/{invoice_id}/payments")
async def pay_invoice(invoice_id: uuid.UUID, data: PaymentCreate, request: Request,
                      current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_billing_permission(current_user, "patient_billing:collect", db)
    clinic_id = active_clinic_id(current_user)
    inv = await _locked_invoice(db, invoice_id, clinic_id)
    pay = await service.add_payment(db, inv, user_id=uuid.UUID(current_user.id),
                                    amount_paise=data.amount_paise, mode=data.mode, reference=data.reference)
    await _record_audit(
        clinic_id, uuid.UUID(current_user.id), "payment", "pb_payment", pay.id,
        {"receipt_number": pay.receipt_number, "amount_paise": pay.amount_paise, "mode": pay.mode,
         "invoice_number": inv.invoice_number}, db, ip_address=_client_ip(request))
    return {"payment": payment_dict(pay, inv.invoice_number), "invoice": invoice_dict(inv)}


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(invoice_id: uuid.UUID, data: CancelBody, request: Request,
                         current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    await _require_billing_permission(current_user, "patient_billing:void", db)
    clinic_id = active_clinic_id(current_user)
    inv = await _locked_invoice(db, invoice_id, clinic_id)
    await service.cancel_invoice(db, inv, data.reason)
    await _record_audit(
        clinic_id, uuid.UUID(current_user.id), "cancel", "pb_invoice", inv.id,
        {"invoice_number": inv.invoice_number, "reason": inv.cancel_reason}, db,
        old_values={"status": "issued"}, ip_address=_client_ip(request))
    return invoice_dict(inv)


@router.post("/accounts/{patient_id}/collect")
async def collect(patient_id: uuid.UUID, data: CollectBody, request: Request,
                  current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """The 'Collect' button: invoices the chosen unbilled charges and takes payment, atomically.
    Needs both the invoice and the collect permission."""
    await _require_billing_permission(current_user, "patient_billing:invoice", db)
    await _require_billing_permission(current_user, "patient_billing:collect", db)
    clinic_id, uid = active_clinic_id(current_user), uuid.UUID(current_user.id)
    inv = await service.create_invoice(
        db, clinic_id=clinic_id, user_id=uid, patient_id=patient_id,
        charge_ids=data.charge_item_ids, discount_paise=data.discount_paise, counter=data.counter)
    pay = None
    if inv.net_paise > 0:
        pay = await service.add_payment(
            db, inv, user_id=uid, amount_paise=data.amount_paise or inv.net_paise,
            mode=data.mode, reference=data.reference)
    await _record_audit(
        clinic_id, uid, "create", "pb_invoice", inv.id,
        {"invoice_number": inv.invoice_number, "net_paise": inv.net_paise,
         "discount_paise": inv.discount_paise, "collected": True}, db, ip_address=_client_ip(request))
    if pay:
        await _record_audit(
            clinic_id, uid, "payment", "pb_payment", pay.id,
            {"receipt_number": pay.receipt_number, "amount_paise": pay.amount_paise, "mode": pay.mode,
             "invoice_number": inv.invoice_number}, db, ip_address=_client_ip(request))
    return {"invoice": invoice_dict(inv), "payment": payment_dict(pay, inv.invoice_number) if pay else None}


@router.get("/payments")
async def list_payments(on_date: Optional[date] = Query(None, alias="date"),
                        patient_id: Optional[uuid.UUID] = None, page: int = 1,
                        page_size: int = Query(25, le=100),
                        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Receipts, newest first."""
    await _require_billing_permission(current_user, "patient_billing:view", db)
    clinic_id = active_clinic_id(current_user)
    q = (select(PbPayment, PbInvoice.invoice_number, PbInvoice.patient_name, PbInvoice.patient_uhid)
         .join(PbInvoice, PbInvoice.id == PbPayment.invoice_id)
         .where(PbPayment.clinic_id == clinic_id, PbPayment.deleted_at.is_(None),
                PbInvoice.status != INV_CANCELLED))
    if on_date:
        q = q.where(PbPayment.paid_on == on_date)
    if patient_id:
        q = q.where(PbPayment.patient_id == patient_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(q.order_by(PbPayment.created_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).all()
    return paginate_response([payment_dict(p, n, name, uhid) for p, n, name, uhid in rows], page, page_size, total)
