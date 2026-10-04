"""Patient Billing — accounts: the billing desk's Pending list, one patient's complete bill,
and the day's collection summary."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from modules.patient_billing.common import _require_billing_permission
from modules.patient_billing.constants import (
    ACC_INVOICED_UNPAID, ACC_NOT_INVOICED, ACC_PART_PAID, ACC_PENDING, ACCOUNT_FILTERS,
    CHG_INVOICED, CHG_UNBILLED, CHG_VOID, INV_CANCELLED, INV_PART_PAID, INVOICE_OPEN_STATUSES)
from modules.patient_billing.models import PbChargeItem, PbInvoice, PbPayment
from modules.patient_billing.responses import charge_dict, invoice_dict, payment_dict
from routers.auth_helpers import User, get_current_user, paginate_response
from services.clinics import active_clinic_id

router = APIRouter(prefix="/api/patient-billing", tags=["patient-billing-accounts"])


async def _owed(db, clinic_id) -> dict:
    """patient_id -> what they owe, split into not-invoiced and invoiced-unpaid."""
    out: dict = {}

    def slot(pid):
        return out.setdefault(pid, {"patient_id": str(pid), "patient_name": "", "patient_uhid": None,
                                    "not_invoiced_paise": 0, "invoiced_unpaid_paise": 0,
                                    "has_part_paid": False, "sources": set(), "last_activity": None})

    for pid, name, uhid, total, last in (await db.execute(
            select(PbChargeItem.patient_id, func.max(PbChargeItem.patient_name),
                   func.max(PbChargeItem.patient_uhid), func.sum(PbChargeItem.total_paise),
                   func.max(PbChargeItem.created_at)).where(
                PbChargeItem.clinic_id == clinic_id, PbChargeItem.status == CHG_UNBILLED,
                PbChargeItem.deleted_at.is_(None)).group_by(PbChargeItem.patient_id))).all():
        s = slot(pid)
        s.update(patient_name=name, patient_uhid=uhid, not_invoiced_paise=int(total), last_activity=last)
    for pid, name, uhid, due, part, last in (await db.execute(
            select(PbInvoice.patient_id, func.max(PbInvoice.patient_name), func.max(PbInvoice.patient_uhid),
                   func.sum(PbInvoice.net_paise - PbInvoice.paid_paise),
                   func.bool_or(PbInvoice.status == INV_PART_PAID), func.max(PbInvoice.updated_at)).where(
                PbInvoice.clinic_id == clinic_id, PbInvoice.status.in_(INVOICE_OPEN_STATUSES),
                PbInvoice.deleted_at.is_(None)).group_by(PbInvoice.patient_id))).all():
        s = slot(pid)
        s.update(patient_name=s["patient_name"] or name, patient_uhid=s["patient_uhid"] or uhid,
                 invoiced_unpaid_paise=int(due), has_part_paid=bool(part))
        s["last_activity"] = max(filter(None, [s["last_activity"], last]))
    for pid, src in (await db.execute(
            select(PbChargeItem.patient_id, PbChargeItem.source_module).where(
                PbChargeItem.clinic_id == clinic_id,
                PbChargeItem.status.in_((CHG_UNBILLED, CHG_INVOICED)),
                PbChargeItem.deleted_at.is_(None)).distinct())).all():
        if pid in out:
            out[pid]["sources"].add(src)
    return out


@router.get("/accounts")
async def list_accounts(status: str = ACC_PENDING, source: Optional[str] = None, search: Optional[str] = None,
                        page: int = 1, page_size: int = Query(25, le=100),
                        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """The billing desk's list. `status=pending` (default) = everyone who owes money."""
    await _require_billing_permission(current_user, "patient_billing:view", db)
    if status not in ACCOUNT_FILTERS:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(ACCOUNT_FILTERS)}")
    owed = await _owed(db, active_clinic_id(current_user))
    rows = []
    for a in owed.values():
        a["balance_paise"] = a["not_invoiced_paise"] + a["invoiced_unpaid_paise"]
        if status == ACC_PENDING and a["balance_paise"] <= 0:
            continue
        if status == ACC_NOT_INVOICED and a["not_invoiced_paise"] <= 0:
            continue
        if status == ACC_INVOICED_UNPAID and a["invoiced_unpaid_paise"] <= 0:
            continue
        if status == ACC_PART_PAID and not a["has_part_paid"]:
            continue
        if source and source not in a["sources"]:
            continue
        if search and search.lower() not in f"{a['patient_name']} {a['patient_uhid'] or ''}".lower():
            continue
        rows.append({**a, "sources": sorted(a["sources"]),
                     "last_activity": a["last_activity"].isoformat() if a["last_activity"] else None})
    rows.sort(key=lambda r: r["balance_paise"], reverse=True)
    totals = {"balance_paise": sum(r["balance_paise"] for r in rows),
              "not_invoiced_paise": sum(r["not_invoiced_paise"] for r in rows),
              "invoiced_unpaid_paise": sum(r["invoiced_unpaid_paise"] for r in rows), "patients": len(rows)}
    body = paginate_response(rows[(page - 1) * page_size: page * page_size], page, page_size, len(rows))
    return {**body, "totals": totals}


@router.get("/accounts/{patient_id}")
async def get_account(patient_id: uuid.UUID, current_user: User = Depends(get_current_user),
                      db: AsyncSession = DbSession):
    """One patient's complete bill: every charge, invoice and payment, with totals."""
    await _require_billing_permission(current_user, "patient_billing:view", db)
    clinic_id = active_clinic_id(current_user)
    charges = (await db.execute(select(PbChargeItem).where(
        PbChargeItem.clinic_id == clinic_id, PbChargeItem.patient_id == patient_id,
        PbChargeItem.deleted_at.is_(None)).order_by(PbChargeItem.created_at))).scalars().all()
    invoices = (await db.execute(select(PbInvoice).where(
        PbInvoice.clinic_id == clinic_id, PbInvoice.patient_id == patient_id,
        PbInvoice.deleted_at.is_(None)).order_by(PbInvoice.created_at))).scalars().all()
    pays = (await db.execute(
        select(PbPayment, PbInvoice.invoice_number).join(PbInvoice, PbInvoice.id == PbPayment.invoice_id)
        .where(PbPayment.clinic_id == clinic_id, PbPayment.patient_id == patient_id,
               PbPayment.deleted_at.is_(None)).order_by(PbPayment.created_at))).all()
    if not charges and not invoices:
        raise HTTPException(status_code=404, detail="No billing account for this patient yet")
    live = [c for c in charges if c.status != CHG_VOID]
    unbilled = sum(c.total_paise for c in live if c.status == CHG_UNBILLED)
    due = sum(i.net_paise - i.paid_paise for i in invoices if i.status in INVOICE_OPEN_STATUSES)
    ref = charges[0] if charges else invoices[0]
    return {
        "patient": {"id": str(patient_id), "name": ref.patient_name, "uhid": ref.patient_uhid},
        "totals": {"total_charges_paise": sum(c.total_paise for c in live),
                   "paid_paise": sum(p.amount_paise for p, _ in pays),
                   "not_invoiced_paise": unbilled, "invoiced_unpaid_paise": due,
                   "balance_paise": unbilled + due},
        "charges": [charge_dict(c) for c in charges],
        "invoices": [invoice_dict(i) for i in invoices if i.status != INV_CANCELLED],
        "payments": [payment_dict(p, n) for p, n in pays],
    }


@router.get("/summary/today")
async def summary_today(on_date: Optional[date] = Query(None, alias="date"),
                        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """What was collected on a day, by payment mode and by counter (feeds Day closing + the queue card)."""
    await _require_billing_permission(current_user, "patient_billing:view", db)
    clinic_id, day = active_clinic_id(current_user), on_date or date.today()
    rows = (await db.execute(
        select(PbPayment.mode, PbInvoice.counter, func.sum(PbPayment.amount_paise), func.count())
        .join(PbInvoice, PbInvoice.id == PbPayment.invoice_id)
        .where(PbPayment.clinic_id == clinic_id, PbPayment.paid_on == day,
               PbPayment.deleted_at.is_(None)).group_by(PbPayment.mode, PbInvoice.counter))).all()
    by_mode: dict = {}
    by_counter: dict = {}
    for mode, counter, amt, _n in rows:
        by_mode[mode] = by_mode.get(mode, 0) + int(amt)
        by_counter[counter] = by_counter.get(counter, 0) + int(amt)
    return {"date": day.isoformat(), "collected_paise": sum(by_mode.values()),
            "receipts": sum(int(n) for *_, n in rows), "by_mode": by_mode, "by_counter": by_counter}
