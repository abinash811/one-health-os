"""Patient Billing service — the ONLY thing other modules import from here.

The HTTP routers and in-process callers (e.g. EMR posting a consultation fee at
check-in) all go through these functions, so there is one set of rules for
charges, invoices and payments. All money is integer paise. Callers pass
already-authorised, tenant-scoped ids; every query here is scoped by
`pharmacy_id` as well."""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.patient_billing.constants import (
    CHG_INVOICED, CHG_PAID, CHG_UNBILLED, CHG_VOID, COUNTERS, INV_CANCELLED, INV_ISSUED,
    INV_PAID, INV_PART_PAID, INVOICE_PREFIX, MAX_AMOUNT_PAISE, PAYMENT_MODES, RECEIPT_PREFIX,
    SOURCE_MODULES, SOURCES_POSTABLE_NOW, SRC_PHARMACY)
from modules.patient_billing.models import PbChargeItem, PbInvoice, PbPayment


def rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


async def _next_number(db: AsyncSession, column, pharmacy_id: uuid.UUID, prefix: str) -> str:
    """Highest trailing number ever issued + 1 — numbers are never reused or restarted."""
    rows = (await db.execute(select(column).where(
        column.class_.pharmacy_id == pharmacy_id))).scalars().all()
    top = max((int(m.group()) for r in rows if (m := re.search(r"\d+$", r))), default=0)
    return f"{prefix}{top + 1:06d}"


# ── Charges ──────────────────────────────────────────────────────────────────

async def post_charge(
    db: AsyncSession, *, pharmacy_id: uuid.UUID, user_id: uuid.UUID, patient_id: uuid.UUID,
    patient_name: str, patient_uhid: Optional[str], source_module: str, description: str,
    unit_price_paise: int, quantity: int = 1, source_ref: Optional[str] = None,
    encounter_ref: Optional[str] = None, encounter_type: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> tuple[PbChargeItem, bool]:
    """Adds a charge to the patient's account. Returns (charge, created). A repeated post with
    the same `idempotency_key` returns the original charge instead of charging twice."""
    if source_module not in SOURCE_MODULES:
        raise HTTPException(status_code=422, detail=f"source_module must be one of {', '.join(SOURCE_MODULES)}")
    if source_module not in SOURCES_POSTABLE_NOW:
        raise HTTPException(
            status_code=422,
            detail="Pharmacy charges are billed from the pharmacy and are not accepted here yet")
    if not description.strip():
        raise HTTPException(status_code=422, detail="A charge needs a description")
    if not 1 <= unit_price_paise <= MAX_AMOUNT_PAISE:
        raise HTTPException(status_code=422, detail="unit_price_paise must be a positive amount")
    if not 1 <= quantity <= 10_000:
        raise HTTPException(status_code=422, detail="quantity must be between 1 and 10000")
    if unit_price_paise * quantity > MAX_AMOUNT_PAISE:
        raise HTTPException(status_code=422, detail="Charge total is too large")

    async def _existing():
        return (await db.execute(select(PbChargeItem).where(
            PbChargeItem.pharmacy_id == pharmacy_id,
            PbChargeItem.idempotency_key == idempotency_key))).scalar_one_or_none()

    if idempotency_key and (found := await _existing()):
        return found, False
    charge = PbChargeItem(
        pharmacy_id=pharmacy_id, patient_id=patient_id, patient_name=patient_name.strip(),
        patient_uhid=patient_uhid, source_module=source_module, source_ref=source_ref,
        encounter_ref=encounter_ref, encounter_type=encounter_type, description=description.strip(),
        quantity=quantity, unit_price_paise=unit_price_paise, total_paise=unit_price_paise * quantity,
        idempotency_key=idempotency_key, created_by=user_id)
    try:
        async with db.begin_nested():
            db.add(charge)
            await db.flush()
    except IntegrityError:
        if idempotency_key and (found := await _existing()):
            return found, False
        raise
    await db.refresh(charge)
    return charge, True


async def void_charge(db: AsyncSession, charge: PbChargeItem, reason: str) -> None:
    """Only an unbilled charge can be voided; an invoiced one needs its invoice cancelled first."""
    if charge.status != CHG_UNBILLED:
        raise HTTPException(
            status_code=409,
            detail=f"A {charge.status} charge cannot be voided"
                   + (" — cancel its invoice first" if charge.status == CHG_INVOICED else ""))
    if not reason.strip():
        raise HTTPException(status_code=422, detail="A reason is required to void a charge")
    charge.status, charge.void_reason = CHG_VOID, reason.strip()
    await db.flush()
    await db.refresh(charge)


async def void_unbilled_by_key(db: AsyncSession, pharmacy_id: uuid.UUID, idempotency_key: str,
                               reason: str) -> Optional[PbChargeItem]:
    """For other modules: withdraw the charge they posted under `idempotency_key`, but only if it is
    still unbilled. Returns the voided charge, or None when there is nothing safe to void."""
    charge = (await db.execute(select(PbChargeItem).where(
        PbChargeItem.pharmacy_id == pharmacy_id, PbChargeItem.idempotency_key == idempotency_key,
        PbChargeItem.status == CHG_UNBILLED).with_for_update())).scalar_one_or_none()
    if not charge:
        return None
    await void_charge(db, charge, reason)
    return charge


async def snapshots_by_key(db: AsyncSession, pharmacy_id: uuid.UUID, keys: list[str]) -> dict[str, dict]:
    """For other modules: where do the charges they posted (by idempotency key) stand right now?
    key -> {charge_id, amount_paise, charge_status, invoice_id, invoice_number, invoice_status,
    paid_paise, balance_paise, mode}. Keys with no charge are simply absent."""
    if not keys:
        return {}
    charges = (await db.execute(select(PbChargeItem).where(
        PbChargeItem.pharmacy_id == pharmacy_id, PbChargeItem.idempotency_key.in_(keys)))).scalars().all()
    inv_ids = [c.invoice_id for c in charges if c.invoice_id]
    invoices = {i.id: i for i in (await db.execute(select(PbInvoice).where(
        PbInvoice.pharmacy_id == pharmacy_id, PbInvoice.id.in_(inv_ids)))).scalars().all()} if inv_ids else {}
    mode_of: dict = {}
    if inv_ids:
        for p in (await db.execute(select(PbPayment).where(
                PbPayment.pharmacy_id == pharmacy_id, PbPayment.invoice_id.in_(inv_ids))
                .order_by(PbPayment.created_at))).scalars().all():
            mode_of[p.invoice_id] = p.mode          # the latest payment's mode wins
    out = {}
    for c in charges:
        inv = invoices.get(c.invoice_id)
        out[c.idempotency_key] = {
            "charge_id": str(c.id), "amount_paise": c.total_paise, "charge_status": c.status,
            "invoice_id": str(inv.id) if inv else None,
            "invoice_number": inv.invoice_number if inv else None,
            "invoice_status": inv.status if inv else None,
            "paid_paise": inv.paid_paise if inv else 0,
            "balance_paise": (inv.net_paise - inv.paid_paise) if inv else c.total_paise,
            "mode": mode_of.get(c.invoice_id) if inv else None}
    return out


# ── Invoices ─────────────────────────────────────────────────────────────────

def _line(c: PbChargeItem) -> dict:
    return {"charge_id": str(c.id), "description": c.description, "quantity": c.quantity,
            "unit_price_paise": c.unit_price_paise, "total_paise": c.total_paise,
            "source_module": c.source_module, "source_ref": c.source_ref}


async def create_invoice(
    db: AsyncSession, *, pharmacy_id: uuid.UUID, user_id: uuid.UUID, patient_id: uuid.UUID,
    charge_ids: list[uuid.UUID], discount_paise: int, counter: str,
) -> PbInvoice:
    """Freezes the chosen UNBILLED charges of one patient into a numbered invoice."""
    ids = list(dict.fromkeys(charge_ids))
    if not ids:
        raise HTTPException(status_code=422, detail="Pick at least one charge to invoice")
    if counter not in COUNTERS:
        raise HTTPException(status_code=422, detail=f"counter must be one of {', '.join(COUNTERS)}")
    charges = (await db.execute(select(PbChargeItem).where(
        PbChargeItem.pharmacy_id == pharmacy_id, PbChargeItem.patient_id == patient_id,
        PbChargeItem.id.in_(ids), PbChargeItem.deleted_at.is_(None)).with_for_update())).scalars().all()
    if len(charges) != len(ids):
        raise HTTPException(status_code=404, detail="One or more charges were not found for this patient")
    if any(c.source_module == SRC_PHARMACY for c in charges):
        raise HTTPException(status_code=422, detail="Pharmacy charges are billed from the pharmacy, not here")
    if any(c.status != CHG_UNBILLED for c in charges):
        raise HTTPException(status_code=409, detail="One or more charges are already billed or void")
    gross = sum(c.total_paise for c in charges)
    if not 0 <= discount_paise <= gross:
        raise HTTPException(status_code=422, detail=f"Discount must be between ₹0 and {rupees(gross)}")
    net = gross - discount_paise
    first = min(charges, key=lambda c: c.created_at)
    invoice = None
    for _ in range(3):
        candidate = PbInvoice(
            pharmacy_id=pharmacy_id, patient_id=patient_id, patient_name=first.patient_name,
            patient_uhid=first.patient_uhid, counter=counter, gross_paise=gross,
            discount_paise=discount_paise, net_paise=net, paid_paise=0,
            status=INV_PAID if net == 0 else INV_ISSUED, lines=[_line(c) for c in charges],
            invoice_number=await _next_number(db, PbInvoice.invoice_number, pharmacy_id, INVOICE_PREFIX),
            created_by=user_id)
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            invoice = candidate
            break
        except IntegrityError:
            continue
    if invoice is None:
        raise HTTPException(status_code=409, detail="Could not number the invoice — please retry")
    for c in charges:
        c.invoice_id = invoice.id
        c.status = CHG_PAID if net == 0 else CHG_INVOICED
    await db.flush()
    await db.refresh(invoice)
    return invoice


async def cancel_invoice(db: AsyncSession, invoice: PbInvoice, reason: str) -> PbInvoice:
    """Cancels an unpaid invoice and returns its charges to 'unbilled'. A paid invoice needs a
    refund, which is not supported yet."""
    if invoice.status == INV_CANCELLED:
        raise HTTPException(status_code=409, detail="Invoice is already cancelled")
    if invoice.paid_paise > 0:
        raise HTTPException(
            status_code=409,
            detail="This invoice has payments on it. Refunds are not supported yet, so it cannot be cancelled")
    if not reason.strip():
        raise HTTPException(status_code=422, detail="A reason is required to cancel an invoice")
    for c in (await db.execute(select(PbChargeItem).where(
            PbChargeItem.invoice_id == invoice.id).with_for_update())).scalars().all():
        c.invoice_id, c.status = None, CHG_UNBILLED
    invoice.status, invoice.cancel_reason = INV_CANCELLED, reason.strip()
    await db.flush()
    await db.refresh(invoice)
    return invoice


# ── Payments ─────────────────────────────────────────────────────────────────

async def add_payment(
    db: AsyncSession, invoice: PbInvoice, *, user_id: uuid.UUID, amount_paise: int, mode: str,
    reference: Optional[str],
) -> PbPayment:
    """Records money against a (row-locked) invoice. Part-payments are fine; paying more than the
    balance is refused. When the balance reaches zero the invoice and its charges become paid."""
    if mode not in PAYMENT_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {', '.join(PAYMENT_MODES)}")
    if invoice.status == INV_CANCELLED:
        raise HTTPException(status_code=409, detail="A cancelled invoice cannot take payment")
    balance = invoice.net_paise - invoice.paid_paise
    if balance <= 0:
        raise HTTPException(status_code=409, detail="This invoice is already fully paid")
    if not 1 <= amount_paise <= MAX_AMOUNT_PAISE:
        raise HTTPException(status_code=422, detail="amount_paise must be a positive amount")
    if amount_paise > balance:
        raise HTTPException(status_code=422, detail=f"Amount exceeds the balance due ({rupees(balance)})")
    payment = None
    for _ in range(3):
        candidate = PbPayment(
            pharmacy_id=invoice.pharmacy_id, patient_id=invoice.patient_id, invoice_id=invoice.id,
            amount_paise=amount_paise, mode=mode, reference=(reference or "").strip() or None,
            receipt_number=await _next_number(db, PbPayment.receipt_number, invoice.pharmacy_id, RECEIPT_PREFIX),
            paid_on=date.today(), received_by=user_id)
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            payment = candidate
            break
        except IntegrityError:
            continue
    if payment is None:
        raise HTTPException(status_code=409, detail="Could not number the receipt — please retry")
    invoice.paid_paise += amount_paise
    invoice.status = INV_PAID if invoice.paid_paise >= invoice.net_paise else INV_PART_PAID
    if invoice.status == INV_PAID:
        for c in (await db.execute(select(PbChargeItem).where(
                PbChargeItem.invoice_id == invoice.id))).scalars().all():
            c.status = CHG_PAID
    await db.flush()
    await db.refresh(invoice)
    await db.refresh(payment)
    return payment
