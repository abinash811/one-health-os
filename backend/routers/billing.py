from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.billing import (
    Bill as BillORM, BillItem as BillItemORM, BillPaymentSplit as BillPaymentSplitORM,
    DayEndClosing as DayEndClosingORM, SalesReturn as SalesReturnORM, ScheduleH1Register,
)
from models.customers import Customer as CustomerORM, Doctor as DoctorORM
from models.pharmacy import Pharmacy, PharmacySettings
from models.products import Product as ProductORM, StockBatch as BatchORM, StockMovement as MovementORM
from models.users import AuditLog, User as UserORM
from routers.auth_helpers import User, get_current_user, get_owned_or_404, has_permission

router = APIRouter(prefix="/api", tags=["billing"])
logger = logging.getLogger(__name__)


# ── Pydantic request models ──────────────────────────────────────────────────

class BillCreate(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    # Schedule H1 register (Drugs & Cosmetics Rules, Rule 65): the patient's
    # name AND address must be recorded at the time of supply, same standing
    # as the prescriber's name/registration — not something a saved customer
    # profile can stand in for, since a one-off walk-in buying a single H1
    # item is exactly who this rule exists for. Age isn't a legal
    # requirement, kept optional.
    patient_address: Optional[str] = None
    patient_age: Optional[int] = None
    # The bill's picked date (BillingSubbar's Date field) — was never sent
    # at all before Sep 19, 2026 (Abinash, direct instruction), so every
    # bill silently got today's date regardless of what was picked here.
    # ISO date string ("YYYY-MM-DD"); falls back to today if omitted.
    bill_date: Optional[str] = None
    items: List[Dict[str, Any]]
    discount: float = 0
    tax_rate: float
    payments: Optional[List[Dict[str, Any]]] = None
    payment_method: Optional[str] = None
    status: str = "paid"
    invoice_type: str = "SALE"
    ref_invoice_id: Optional[str] = None
    refund: Optional[Dict[str, Any]] = None

    # bills.customer_phone is VARCHAR(10) (models/billing.py) — same class of
    # bug as customers.phone (see routers/customers.py): an unvalidated
    # overlong value reaches asyncpg and crashes with a raw 500
    # (StringDataRightTruncationError) instead of a clean 422.
    @field_validator("customer_mobile")
    @classmethod
    def _validate_customer_mobile_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 10:
            raise ValueError("Customer mobile number must be at most 10 characters")
        return v


class PaymentCreate(BaseModel):
    invoice_id: str
    amount: float
    payment_method: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class RefundCreate(BaseModel):
    return_invoice_id: str
    original_invoice_id: Optional[str] = None
    amount: float
    refund_method: str
    reference_number: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_bill_date(bill_date_str: Optional[str]) -> date:
    """Parses the picked bill date, defaulting to today when omitted (an
    older client, or a caller that never sends it). Rejects a future date —
    same constraint BillingSubbar's own calendar already enforces
    client-side (`disabled={(date) => date > new Date()}`), enforced again
    here since the frontend guard alone can't stop a direct API call."""
    if not bill_date_str:
        return date.today()
    parsed = date.fromisoformat(bill_date_str[:10])
    if parsed > date.today():
        raise HTTPException(status_code=400, detail="Bill date cannot be in the future.")
    return parsed


async def _generate_bill_number(pharmacy_id: uuid.UUID, db: AsyncSession) -> str:
    # This generates Sales Invoice numbers only. Sales Returns (credit notes)
    # never go through this function — they're their own resource at
    # POST /sales-returns with their own sequence (sales_returns.py's
    # _generate_credit_note_number), because GST requires the two to be
    # separate, gapless number series.
    result = await db.execute(select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = result.scalar_one_or_none()

    prefix = ps.bill_prefix if ps else "INV"
    length = ps.bill_number_length if ps else 6
    seq = ps.bill_sequence_number if ps else 1

    bill_number = f"{prefix}-{str(seq).zfill(length)}"

    # Increment sequence
    if ps:
        ps.bill_sequence_number = seq + 1
    else:
        ps = PharmacySettings(pharmacy_id=pharmacy_id, bill_sequence_number=2)
        db.add(ps)

    return bill_number


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID,
    old_values: dict | None, new_values: dict | None, db: AsyncSession,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        old_values=old_values, new_values=new_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    # AuditLog.ip_address was defined on the schema since the app's start
    # but no caller ever passed one — always NULL. Trusts the direct
    # connecting peer only (request.client.host); this app has no reverse
    # proxy / X-Forwarded-For handling anywhere yet, so honoring that
    # header here would let a client spoof its own logged IP.
    return request.client.host if request.client else None


def _bill_response(
        b: BillORM, items: list[BillItemORM],
        payment_splits: Optional[list[dict]] = None) -> dict:
    """`payment_splits` — already-normalized [{"method", "amount"}]
    (rupees) list for a "Multi"-paid bill; empty/None for an ordinary
    single-method bill, same as no payment_method at all."""
    return {
        "id": str(b.id),
        "bill_number": b.bill_number,
        "invoice_type": b.invoice_type,
        "status": b.status,
        "customer_id": str(b.customer_id) if b.customer_id else None,
        "customer_name": b.customer_name,
        "customer_mobile": b.customer_phone,
        "doctor_id": str(b.doctor_id) if b.doctor_id else None,
        "doctor_name": b.doctor_name,
        "items": [_bill_item_response(i) for i in items],
        "subtotal": b.subtotal_paise / 100,
        "discount": b.total_discount_paise / 100,
        "tax_rate": 0,
        "tax_amount": b.total_gst_paise / 100,
        "total_amount": b.grand_total_paise / 100,
        # grand_total_paise is rounded to the nearest rupee at create time
        # (see create_bill) — round_off is whatever remains after every
        # other explicit term, not a fake constant. Same derivation as
        # purchases.py's _purchase_response.
        "round_off": (b.grand_total_paise - (
            b.subtotal_paise + b.total_gst_paise - b.bill_discount_paise
        )) / 100,
        "paid_amount": b.amount_paid_paise / 100,
        "due_amount": b.balance_paise / 100,
        "payment_method": b.payment_method,
        "payment_splits": payment_splits or [],
        "cashier_id": str(b.billed_by) if b.billed_by else None,
        "cashier_name": "",
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        # Same gap as _bill_list_response above — also read by
        # BillingWorkspace's loadExistingBill (Continue Bill / same-day
        # correction), which fell back to created_at here too.
        "bill_date": b.bill_date.isoformat() if b.bill_date else None,
    }


def _bill_item_response(i: BillItemORM) -> dict:
    return {
        "id": str(i.id),
        "product_id": str(i.product_id),
        "product_name": i.product_name,
        "batch_id": str(i.batch_id),
        "batch_no": i.batch_number,
        "batch_number": i.batch_number,
        "expiry_date": i.expiry_date.isoformat() if i.expiry_date else None,
        "quantity": i.quantity,
        "unit_price": i.sale_price_paise / 100,
        "mrp": i.mrp_paise / 100,
        "cost_price": i.cost_price_paise / 100,
        "discount": float(i.discount_percent),
        "disc_percent": float(i.discount_percent),
        "gst_percent": float(i.gst_rate),
        "line_total": i.line_total_paise / 100,
        "total": i.line_total_paise / 100,
        "product_sku": "",
        "medicine_name": i.product_name,
        "schedule": i.drug_schedule,
    }


def _bill_list_response(b: BillORM) -> dict:
    return {
        "id": str(b.id),
        "bill_number": b.bill_number,
        "invoice_type": b.invoice_type or "SALE",
        "status": b.status or "paid",
        "customer_name": b.customer_name,
        "customer_mobile": b.customer_phone,
        "doctor_name": b.doctor_name,
        "subtotal": b.subtotal_paise / 100,
        "discount": b.total_discount_paise / 100,
        "tax_amount": b.total_gst_paise / 100,
        "total_amount": b.grand_total_paise / 100,
        "paid_amount": b.amount_paid_paise / 100,
        "due_amount": b.balance_paise / 100,
        "payment_method": b.payment_method,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        # Was missing entirely — found Sep 19, 2026 (Abinash, testing a
        # backdated bill): the frontend's "Bill Date" column and
        # "Backdated" badge both read bill.bill_date from this response
        # and always fell back to created_at, so a genuinely backdated
        # bill (correctly saved in the DB — bill_date itself was fixed in
        # the previous commit) still looked identical to a normal one in
        # the list, because this endpoint never sent the real value.
        "bill_date": b.bill_date.isoformat() if b.bill_date else None,
    }


async def _resolve_batch(item: dict, pharmacy_id: uuid.UUID,
                         db: AsyncSession) -> tuple[BatchORM | None, ProductORM | None]:
    """Resolve a batch and product from bill item data."""
    batch: BatchORM | None = None
    product: ProductORM | None = None
    batch_id = item.get("batch_id")
    product_id = item.get("product_id") or item.get("medicine_id")
    product_sku = item.get("product_sku")
    batch_no = item.get("batch_no") or item.get("batch_number")

    # Try batch by ID
    if batch_id:
        try:
            result = await db.execute(select(BatchORM).where(
                BatchORM.id == uuid.UUID(batch_id), BatchORM.pharmacy_id == pharmacy_id))
            batch = result.scalar_one_or_none()
        except ValueError:
            pass

    # Try batch by product + batch_number
    if not batch and product_sku and batch_no:
        prod_result = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == pharmacy_id,
                ProductORM.sku == product_sku)
        )
        product = prod_result.scalar_one_or_none()
        if product:
            batch_result = await db.execute(
                select(BatchORM).where(
                    BatchORM.pharmacy_id == pharmacy_id,
                    BatchORM.product_id == product.id,
                    BatchORM.batch_number == batch_no)
            )
            batch = batch_result.scalar_one_or_none()

    # Try batch by product_id FEFO
    if not batch and product_id:
        try:
            pid = uuid.UUID(product_id)
            batch_result = await db.execute(
                select(BatchORM).where(
                    BatchORM.pharmacy_id == pharmacy_id,
                    BatchORM.product_id == pid,
                    BatchORM.quantity_on_hand > 0,
                    BatchORM.is_active)
                .order_by(BatchORM.expiry_date).limit(1)
            )
            batch = batch_result.scalar_one_or_none()
        except ValueError:
            pass

    # Resolve product if not yet found
    if batch and not product:
        prod_result = await db.execute(select(ProductORM).where(
            ProductORM.id == batch.product_id, ProductORM.pharmacy_id == pharmacy_id))
        product = prod_result.scalar_one_or_none()
    if not product and product_id:
        try:
            prod_result = await db.execute(select(ProductORM).where(
                ProductORM.id == uuid.UUID(product_id), ProductORM.pharmacy_id == pharmacy_id))
            product = prod_result.scalar_one_or_none()
        except ValueError:
            pass
    if not product and product_sku:
        prod_result = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == pharmacy_id,
                ProductORM.sku == product_sku)
        )
        product = prod_result.scalar_one_or_none()

    return batch, product


async def _deduct_stock_and_record(
    batch: BatchORM, product: ProductORM, quantity: int, is_sale: bool,
    bill_id: uuid.UUID, pharmacy_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession,
) -> None:
    """Deduct (or restore) stock and create a movement record.

    quantity is already in real units, same as quantity_on_hand — see
    models/products.py's StockBatch comment (migration a343c922f896).
    units_per_pack is never applied to a stored quantity.
    """
    old_qty = batch.quantity_on_hand

    if is_sale:
        if old_qty < quantity:
            raise HTTPException(
                status_code=400,
                detail=(f"Insufficient stock for {product.name} in batch {batch.batch_number}: "
                        f"{old_qty} available, {quantity} requested"))
        batch.quantity_on_hand = old_qty - quantity
        batch.quantity_sold = (batch.quantity_sold or 0) + quantity
        qty_delta = -quantity
    else:
        batch.quantity_on_hand = old_qty + quantity
        qty_delta = quantity

    db.add(MovementORM(
        pharmacy_id=pharmacy_id, product_id=product.id, batch_id=batch.id,
        movement_type="sale" if is_sale else "sales_return",
        quantity=qty_delta,
        quantity_before=old_qty, quantity_after=batch.quantity_on_hand,
        reference_type="invoice", reference_id=bill_id,
        user_id=user_id, notes=None,
    ))


async def _create_h1_entry(
    product: ProductORM, batch: BatchORM, quantity: int,
    bill: BillORM, bill_item: BillItemORM,
    doctor_name: str | None, customer_name: str | None,
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession,
    patient_address: str | None = None, patient_age: int | None = None,
) -> None:
    """Create Schedule H1 register entry if product is H1."""
    if product.drug_schedule != "H1":
        return

    prescriber_address = ""
    prescriber_reg = ""
    if doctor_name:
        doc_result = await db.execute(
            select(DoctorORM).where(
                DoctorORM.pharmacy_id == pharmacy_id,
                func.lower(DoctorORM.name) == doctor_name.lower(),
            )
        )
        doctor = doc_result.scalar_one_or_none()
        if doctor:
            prescriber_address = doctor.address or ""
            prescriber_reg = doctor.registration_number or doctor.phone or ""

    db.add(ScheduleH1Register(
        pharmacy_id=pharmacy_id,
        bill_id=bill.id,
        bill_item_id=bill_item.id,
        product_id=product.id,
        product_name=product.name,
        quantity=quantity,
        batch_number=batch.batch_number,
        prescriber_name=doctor_name or "N/A",
        prescriber_registration_number=prescriber_reg,
        prescriber_address=prescriber_address,
        patient_name=customer_name or "Walk-in Customer",
        patient_address=patient_address,
        patient_age=patient_age,
        dispensed_by=user_id,
    ))


# Due bills (and the credit-limit check that gated them) were removed Sep
# 19, 2026 (Abinash, direct instruction) — a bill must be paid in full to
# finalize, so there is no more "outstanding balance" to check against a
# limit. `_check_credit_limit` and its caller in create_bill/update_bill
# were deleted rather than left as dead code.

# "Multi" is only for a fully-paid bill split across real payment
# instruments — "due" as a split leg would mean "not paid," which is
# what the separate Due flow (BillingSubbar's own paid_now/balance
# handling) already covers; combining the two is real scope, not built.
# "card" split into "credit_card"/"debit_card" Sep 24, 2026 (Abinash, direct
# instruction) — see domainConstants.js's PAYMENT_METHOD comment (frontend)
# for why. Old bills whose payment_splits already contain "card" are never
# rewritten (Manifesto rule 6); this whitelist only gates NEW writes.
_VALID_SPLIT_METHODS = {"cash", "upi", "credit_card", "debit_card"}


def _resolve_payment_splits(
        payments: Optional[List[Dict[str, Any]]], grand_total_paise: int,
) -> tuple[Optional[str], int, list[dict]]:
    """Resolve a bill's real payment_method plus, for a genuine "Multi"
    payment (2+ legs in `payments`), the validated per-leg split to
    persist as BillPaymentSplit rows and in the audit log.

    Added Sep 16, 2026 — "Multi" used to be a pill that set
    payment_method="multiple" with no split-entry UI behind it and
    nowhere the real breakdown was stored (found in the Billing
    product-review, the pill itself removed Sep 13, 2026 rather than ship
    that). Shared between create_bill and update_bill's finalize path —
    the exact "reached one entry point, not the other" shape Manifesto
    rule 11 exists to catch.

    Returns (resolved_payment_method, paid_paise, splits). A single-leg
    (or absent) `payments` array is unchanged prior behavior — the caller
    still reads its own payment_method/paid_paise the way it always did;
    this only activates for 2+ legs.
    """
    if not payments or len(payments) < 2:
        return None, 0, []

    splits: list[dict] = []
    total_paise = 0
    for leg in payments:
        method = leg.get("method") or leg.get("payment_method")
        if method not in _VALID_SPLIT_METHODS:
            raise HTTPException(
                status_code=400,
                detail=(f"Invalid split payment method: {method!r}. "
                        f"Must be one of cash, upi, card."))
        amount_paise = int(round((leg.get("amount") or 0) * 100))
        if amount_paise <= 0:
            raise HTTPException(
                status_code=400, detail="Each split payment amount must be greater than zero.")
        splits.append({"method": method, "amount_paise": amount_paise})
        total_paise += amount_paise

    if total_paise != grand_total_paise:
        raise HTTPException(
            status_code=400,
            detail=(f"Split payments must add up to the bill total exactly — "
                    f"got ₹{total_paise / 100:.2f}, expected ₹{grand_total_paise / 100:.2f}."))

    return "multiple", total_paise, splits


async def _save_payment_splits(bill_id: uuid.UUID, splits: list[dict], db: AsyncSession) -> None:
    for leg in splits:
        db.add(BillPaymentSplitORM(
            bill_id=bill_id, payment_method=leg["method"], amount_paise=leg["amount_paise"]))


# ── /bills ─────────────────────────────────────────────────────────────────────

@router.post("/bills")
async def create_bill(bill_data: BillCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # permission-exempt: app-wide Billing RBAC rollout is an explicit, undecided
    # product decision (docs/15_ROADMAP.md KNOWN ISSUES) — gating this blind risks
    # locking cashiers out of billing itself; do not add a check here without asking
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    user_id = uuid.UUID(current_user.id)
    is_draft = bill_data.status == "draft"
    is_sale = bill_data.invoice_type == "SALE"

    # Settings-driven checks. Read-only here: never db.add()s a missing row,
    # so this can't race _generate_bill_number's own fetch-or-create below
    # when both run in the same request (SQLAlchemy's identity map dedupes
    # the read once a row exists; when none exists yet, only the writer
    # creates one).
    # Was previously gated behind "not is_draft and is_sale" (expiry checks
    # only matter for a real finalizing sale) — now fetched unconditionally
    # since enable_draft_bills/default_gst_rate/round_off_amount matter for
    # a draft too, and GST/rounding apply to every bill regardless of status.
    bs_result = await db.execute(
        select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    bs = bs_result.scalar_one_or_none()
    block_expired_stock = bs.block_expired_stock if bs else True
    allow_near_expiry_sale = bs.allow_near_expiry_sale if bs else True
    near_expiry_days = bs.near_expiry_threshold_days if bs else 90
    default_gst_rate = float(bs.default_gst_rate) if bs else 5.0
    round_off_amount = bs.round_off_amount if bs else True
    today_for_expiry = date.today()

    # Settings → Billing "Enable draft bills" — found Sep 13, 2026 (Settings
    # product-review): this toggle saved but was never read anywhere, so
    # turning it off had zero effect. Only gates *creating* a new draft
    # (Park Bill) — an existing draft can still be edited/finalized via
    # update_bill regardless, so disabling this can't strand prior work.
    if is_draft and bs and not bs.enable_draft_bills:
        raise HTTPException(
            status_code=400,
            detail="Draft bills are disabled in Settings → Billing preferences.")

    # Drafts use a per-bill unique placeholder so concurrent/repeated drafts don't
    # collide on the UNIQUE(pharmacy_id, bill_number) constraint. Finalized bills
    # get a real sequential number via _generate_bill_number.
    if is_draft:
        bill_number = f"DRAFT-{uuid.uuid4().hex[:8].upper()}"
    else:
        bill_number = await _generate_bill_number(pharmacy_id, db)

    # A valid, non-expired Drug License is required to finalize a real sale —
    # mirrors the check the frontend does proactively before showing the
    # billing screen at all (see BillingWorkspace's DrugLicenseRequiredState).
    # This is the defense-in-depth backstop, not the primary UX.
    if not is_draft and is_sale:
        pharm_result = await db.execute(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
        pharmacy = pharm_result.scalar_one_or_none()
        if not pharmacy or not (pharmacy.drug_license_number or "").strip():
            raise HTTPException(
                status_code=400, detail="A Drug License Number is required to create bills."
            )
        if pharmacy.drug_license_expiry and pharmacy.drug_license_expiry < date.today():
            raise HTTPException(
                status_code=400,
                detail="Your Drug License has expired. Renew it before creating bills.",
            )

    # Calculate totals from items
    subtotal_paise = 0
    mrp_total_paise = 0
    item_discount_paise = 0
    gst_paise = 0
    cost_total_paise = 0
    item_orms: list[tuple[BillItemORM, BatchORM, ProductORM]] = []

    for item in bill_data.items:
        batch, product = await _resolve_batch(item, pharmacy_id, db)
        if not batch or not product:
            if not is_draft:
                logger.warning(
                    f"No batch/product found for item {item.get('product_name', 'unknown')}")
            continue

        # H1 doctor requirement, checked here (once the real product is
        # resolved) rather than in a separate product_sku-only pre-pass, so
        # it also applies to items identified by product_id/batch_id — those
        # used to skip the check entirely.
        if not is_draft and is_sale and product.drug_schedule == "H1" and (
                not bill_data.doctor_name or not bill_data.doctor_name.strip()):
            raise HTTPException(
                status_code=400,
                detail=f"Prescription details required for Schedule H1 drug: {product.name}")

        # H1 patient-address requirement — same standing as the doctor
        # check above (Rule 65: patient name AND address recorded at time
        # of supply). A saved Customer's own address can't be relied on:
        # `customer_name` is often just "Walk-in Customer" with no linked
        # record at all, exactly the one-off sale this rule is for.
        if not is_draft and is_sale and product.drug_schedule == "H1" and (
                not bill_data.patient_address or not bill_data.patient_address.strip()):
            raise HTTPException(
                status_code=400,
                detail=f"Patient address required for Schedule H1 drug: {product.name}")

        quantity = item.get("quantity", 0)
        mrp_paise = int(item.get("unit_price", item.get("mrp", 0)) * 100)

        # DPCO forbids selling above MRP — the batch's own recorded MRP
        # (from purchase) is the source of truth, not whatever price the
        # request claims. Drafts are exempt (not a finalized sale yet).
        if not is_draft and is_sale and mrp_paise > batch.mrp_paise:
            raise HTTPException(
                status_code=400,
                detail=(f"Selling price ₹{mrp_paise / 100:.2f} for {product.name} exceeds "
                        f"MRP ₹{batch.mrp_paise / 100:.2f} for batch {batch.batch_number}"))

        # Settings → Inventory "Block expired stock from billing" / "Allow
        # selling near-expiry products" — previously UI-only toggles that
        # were hardcoded True server-side and never checked here at all
        # (see docs/15_ROADMAP.md RULE MISSES LOG). Both default True, so a
        # pharmacy that never touched these settings sees no behavior
        # change beyond expired stock now actually being blocked, which is
        # what the toggle already claimed to do.
        if not is_draft and is_sale and block_expired_stock and batch.expiry_date < today_for_expiry:
            raise HTTPException(
                status_code=400,
                detail=(f"{product.name} (batch {batch.batch_number}) expired on "
                        f"{batch.expiry_date.isoformat()} and cannot be sold."))
        if (not is_draft and is_sale and not allow_near_expiry_sale
                and today_for_expiry <= batch.expiry_date
                < today_for_expiry + timedelta(days=near_expiry_days)):
            raise HTTPException(
                status_code=400,
                detail=(f"{product.name} (batch {batch.batch_number}) is near expiry "
                        f"({batch.expiry_date.isoformat()}) — near-expiry sales are "
                        f"disabled in Settings → Inventory."))

        sale_price_paise = mrp_paise
        disc_percent = item.get("disc_percent", item.get("discount_percent", 0))
        disc_paise = int(mrp_paise * quantity * disc_percent / 100)
        taxable_paise = mrp_paise * quantity - disc_paise
        gst_rate = item.get("gst_percent", bill_data.tax_rate or default_gst_rate)
        line_gst_paise = int(taxable_paise * gst_rate / 100)
        line_total_paise = taxable_paise + line_gst_paise
        line_cost_paise = batch.cost_price_paise * quantity

        bill_item = BillItemORM(
            product_id=product.id,
            batch_id=batch.id,
            product_name=item.get("product_name", item.get("medicine_name", product.name)),
            generic_name=product.generic_name,
            batch_number=batch.batch_number,
            expiry_date=batch.expiry_date,
            hsn_code=product.hsn_code,
            drug_schedule=product.drug_schedule,
            quantity=quantity,
            mrp_paise=mrp_paise,
            sale_price_paise=sale_price_paise,
            cost_price_paise=batch.cost_price_paise,
            discount_percent=disc_percent,
            discount_paise=disc_paise,
            gst_rate=gst_rate,
            cgst_rate=gst_rate / 2,
            sgst_rate=gst_rate / 2,
            taxable_amount_paise=taxable_paise,
            cgst_paise=line_gst_paise // 2,
            sgst_paise=line_gst_paise - line_gst_paise // 2,
            gst_paise=line_gst_paise,
            line_total_paise=line_total_paise,
            line_cost_paise=line_cost_paise,
        )
        item_orms.append((bill_item, batch, product))
        subtotal_paise += taxable_paise
        mrp_total_paise += mrp_paise * quantity
        item_discount_paise += disc_paise
        gst_paise += line_gst_paise
        cost_total_paise += line_cost_paise

    bill_discount_paise = int((bill_data.discount or 0) * 100)
    total_discount_paise = item_discount_paise + bill_discount_paise
    grand_total_paise = subtotal_paise + gst_paise - bill_discount_paise
    # Settings → Tax & GST "Round off amount" — found Sep 13, 2026
    # (Settings product-review): rounding used to happen unconditionally,
    # so this toggle saved but had no effect either way.
    if round_off_amount:
        grand_total_paise = round(grand_total_paise / 100) * 100  # round to nearest rupee

    # Determine payment
    paid_paise = 0
    resolved_payment_method, multi_paid_paise, payment_splits = _resolve_payment_splits(
        bill_data.payments, grand_total_paise)
    if resolved_payment_method:
        bill_data.payment_method = resolved_payment_method
        paid_paise = multi_paid_paise
    elif bill_data.payments:
        paid_paise = sum(int(p.get("amount", 0) * 100) for p in bill_data.payments)
    elif bill_data.invoice_type == "SALES_RETURN" and bill_data.refund:
        paid_paise = int(bill_data.refund.get("amount", grand_total_paise / 100) * 100)
    elif bill_data.payment_method and bill_data.status == "paid":
        paid_paise = grand_total_paise

    balance_paise = max(0, grand_total_paise - paid_paise)

    if is_draft:
        status = "draft"
    elif bill_data.invoice_type == "SALES_RETURN" and bill_data.refund:
        status = "paid"
    elif balance_paise <= 0:
        status = "paid"
    else:
        # Sep 19, 2026 product decision (Abinash, direct instruction):
        # "Due"/partial-payment bills are removed — a bill must be paid in
        # full to finalize, full stop. This is the real enforcement point;
        # blocking only in the frontend would leave a direct API call able
        # to still create one. Parking a bill as a draft (unpaid, not yet
        # finalized) is unaffected — only a finalized bill must be paid in
        # full.
        raise HTTPException(
            status_code=400,
            detail=(
                f"This bill is short by ₹{balance_paise / 100:.2f} — "
                "a bill must be paid in full to finalize. Park it as a "
                "draft instead if payment isn't ready yet."
            ),
        )

    margin_paise = grand_total_paise - cost_total_paise
    margin_percent = (margin_paise / grand_total_paise * 100) if grand_total_paise > 0 else 0

    # A customer_id/doctor_id supplied here is caller-controlled — without
    # this check, a bill could be linked to another pharmacy's customer or
    # doctor record (polluting their purchase-history stats with a bill
    # they never made), the same cross-tenant class this file's other
    # lookups were fixed for. get_owned_or_404 just verifies ownership; the
    # row itself isn't otherwise used here.
    if bill_data.customer_id:
        await get_owned_or_404(
            db, CustomerORM, bill_data.customer_id, pharmacy_id, not_found_detail="Customer not found")
    if bill_data.doctor_id:
        await get_owned_or_404(
            db, DoctorORM, bill_data.doctor_id, pharmacy_id, not_found_detail="Doctor not found")

    # Nothing stopped this from creating a real, finalized "Paid" tax
    # invoice with zero items — either bill_data.items arrived empty, or
    # every item's batch/product silently failed to resolve (the `continue`
    # above). Both used to fall through to a ₹0.00 invoice, burning a real
    # sequential GST invoice number for nothing. Reject before a Bill row
    # (and its invoice number) is ever created — after the ownership checks
    # above, so a cross-tenant customer_id/doctor_id still correctly 404s
    # regardless of what the caller put in items.
    if not item_orms:
        raise HTTPException(
            status_code=400,
            detail="Add at least one medicine to create a bill.")

    bill = BillORM(
        pharmacy_id=pharmacy_id,
        bill_number=bill_number,
        invoice_type=bill_data.invoice_type or "SALE",
        bill_date=_resolve_bill_date(bill_data.bill_date),
        customer_id=uuid.UUID(bill_data.customer_id) if bill_data.customer_id else None,
        customer_name=bill_data.customer_name,
        customer_phone=bill_data.customer_mobile,
        doctor_id=uuid.UUID(bill_data.doctor_id) if bill_data.doctor_id else None,
        doctor_name=bill_data.doctor_name,
        subtotal_paise=subtotal_paise,
        mrp_total_paise=mrp_total_paise,
        item_discount_paise=item_discount_paise,
        bill_discount_paise=bill_discount_paise,
        total_discount_paise=total_discount_paise,
        taxable_amount_paise=subtotal_paise,
        total_cgst_paise=gst_paise // 2,
        total_sgst_paise=gst_paise - gst_paise // 2,
        total_gst_paise=gst_paise,
        grand_total_paise=grand_total_paise,
        amount_paid_paise=paid_paise,
        balance_paise=balance_paise,
        payment_method=bill_data.payment_method,
        cost_total_paise=cost_total_paise,
        margin_paise=margin_paise,
        margin_percent=round(margin_percent, 2),
        status=status,
        billed_by=user_id,
    )
    db.add(bill)
    await db.flush()

    if payment_splits:
        await _save_payment_splits(bill.id, payment_splits, db)

    # Create bill items and handle stock
    final_items: list[BillItemORM] = []
    for bill_item, batch, product in item_orms:
        bill_item.bill_id = bill.id
        db.add(bill_item)
        await db.flush()
        final_items.append(bill_item)

        if not is_draft:
            await _deduct_stock_and_record(
                batch, product, bill_item.quantity, is_sale, bill.id, pharmacy_id, user_id, db)
            if is_sale:
                await _create_h1_entry(
                    product, batch, bill_item.quantity, bill, bill_item,
                    bill_data.doctor_name, bill_data.customer_name, pharmacy_id, user_id, db,
                    bill_data.patient_address, bill_data.patient_age)

    await _record_audit(
        pharmacy_id, user_id, "create", "invoice", bill.id, None,
        {"bill_number": bill_number, "invoice_type": bill.invoice_type, "status": status,
         "customer_name": bill.customer_name, "total_amount": grand_total_paise / 100,
         "paid_amount": paid_paise / 100, "due_amount": balance_paise / 100,
         # payment_method — read by reports.py's Day-End Closing breakdown
         # as the immutable record of how much/which method was actually
         # collected AT CREATION time, since Bill.payment_method itself
         # gets overwritten by a later POST /payments collection.
         "payment_method": bill.payment_method,
         # payment_splits — added Sep 16, 2026 for "Multi" — Day-End
         # Closing explodes this into its own per-method buckets instead
         # of lumping the whole amount under the meaningless "multiple"
         # key. Rupees here (not paise) to match paid_amount/due_amount's
         # own units in this same audit payload.
         "payment_splits": [{"method": s["method"], "amount": s["amount_paise"] / 100}
                            for s in payment_splits] if payment_splits else None},
        db, ip_address=_client_ip(request),
    )
    await db.flush()

    normalized_splits = [{"method": s["method"], "amount": s["amount_paise"] / 100} for s in payment_splits]
    return _bill_response(bill, final_items, normalized_splits)


@router.put("/bills/{bill_id}")
async def update_bill(bill_id: str, bill_data: BillCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # permission-exempt: same pending app-wide Billing RBAC decision as create_bill above
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    user_id = uuid.UUID(current_user.id)

    bill = await get_owned_or_404(db, BillORM, bill_id, pharmacy_id, not_found_detail="Bill not found")
    bid = bill.id
    if bill.status not in ("draft", "paid", "due"):
        raise HTTPException(status_code=400, detail=f"Bills with status '{bill.status}' cannot be edited")

    # Same-day edit window for a finalized bill (direct product decision,
    # Sep 18 2026 — see docs/15_ROADMAP.md's Billing table). Locked forever
    # once either condition below holds — from there, only a Sales Return
    # can correct it, never a silent rewrite: (1) a Sales Return already
    # exists against this bill (editing now would fight the return over the
    # same line items/stock); (2) that day's Day-End Closing has already
    # run (books are closed for the day).
    was_finalized = bill.status in ("paid", "due")
    if was_finalized:
        return_exists = (await db.execute(
            select(SalesReturnORM.id).where(SalesReturnORM.original_bill_id == bid).limit(1)
        )).scalar_one_or_none()
        if return_exists:
            raise HTTPException(
                status_code=400,
                detail="This bill has a return recorded against it and can no longer be edited.")
        already_closed = (await db.execute(
            select(DayEndClosingORM.id).where(
                DayEndClosingORM.pharmacy_id == pharmacy_id,
                DayEndClosingORM.closing_date == bill.bill_date,
            ).limit(1)
        )).scalar_one_or_none()
        if already_closed:
            raise HTTPException(
                status_code=400,
                detail="This bill's day has already been closed and can no longer be edited.")

    old_bill_snapshot = {
        "grand_total": bill.grand_total_paise / 100, "status": bill.status,
        "customer_name": bill.customer_name, "payment_method": bill.payment_method,
    } if was_finalized else None
    old_paid_paise = bill.amount_paid_paise
    old_payment_method = bill.payment_method

    # Delete old items — reversing their stock effect first if the bill was
    # already finalized (a draft never touched stock, nothing to reverse).
    old_items_result = await db.execute(select(BillItemORM).where(BillItemORM.bill_id == bid))
    old_items = old_items_result.scalars().all()
    if was_finalized:
        # old_item is a child row of the already-scoped bill (tenant-safe below)
        for old_item in old_items:
            batch_q = select(BatchORM).where(BatchORM.id == old_item.batch_id)  # tenant-safe: see above
            batch = (await db.execute(batch_q)).scalar_one_or_none()
            prod_q = select(ProductORM).where(ProductORM.id == old_item.product_id)  # tenant-safe: see above
            product = (await db.execute(prod_q)).scalar_one_or_none()
            if batch and product:
                old_was_sale = bill.invoice_type == "SALE"
                await _deduct_stock_and_record(
                    batch, product, old_item.quantity, not old_was_sale, bid, pharmacy_id, user_id, db)
        # H1 register rows are a legal dispensing record (Rule 65) — detach
        # rather than delete, so the original entry survives permanently
        # even though the bill_item it pointed at is about to be removed.
        # A fresh entry is created below for the rebuilt items.
        h1_result = await db.execute(
            select(ScheduleH1Register).where(ScheduleH1Register.bill_id == bid))
        for h1_entry in h1_result.scalars().all():
            h1_entry.bill_item_id = None
    for old_item in old_items:
        await db.delete(old_item)
    await db.flush()

    # Rebuild items
    subtotal_paise = 0
    mrp_total_paise = 0
    item_discount_paise = 0
    gst_paise = 0
    cost_total_paise = 0
    item_orms: list[tuple[BillItemORM, BatchORM, ProductORM]] = []

    new_status_preview = bill_data.status or "draft"
    # A same-day edit to an already-finalized bill (was_finalized) produces
    # another real, binding sale record just as much as finalizing a draft
    # does — the legal/safety guards below (H1 prescriber, MRP cap, expired/
    # near-expiry stock) must re-apply to it, not just to the draft path.
    is_finalizing_preview = (new_status_preview == "paid" and bill.status == "draft") or was_finalized
    is_sale_preview = bill_data.invoice_type == "SALE"

    # See the identical block in create_bill for why this is safe to
    # read-only-fetch here without racing _generate_bill_number's own
    # fetch-or-create later in this function. Fetched unconditionally (not
    # just when finalizing) since default_gst_rate/round_off_amount apply
    # to every save, same as create_bill.
    bs_result = await db.execute(
        select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    bs = bs_result.scalar_one_or_none()
    block_expired_stock = bs.block_expired_stock if bs else True
    allow_near_expiry_sale = bs.allow_near_expiry_sale if bs else True
    near_expiry_days = bs.near_expiry_threshold_days if bs else 90
    default_gst_rate = float(bs.default_gst_rate) if bs else 5.0
    round_off_amount = bs.round_off_amount if bs else True
    today_for_expiry = date.today()

    for item in bill_data.items:
        batch, product = await _resolve_batch(item, pharmacy_id, db)
        if not batch or not product:
            continue

        # Same checks as create_bill — this loop is the *other* path that can
        # finalize a bill into a real paid sale (editing a draft to "paid"),
        # so it needs the same H1/MRP guards, not just the stock one (that
        # one's covered since _deduct_stock_and_record is shared below).
        if is_finalizing_preview and is_sale_preview and product.drug_schedule == "H1" and (
                not bill_data.doctor_name or not bill_data.doctor_name.strip()):
            raise HTTPException(
                status_code=400,
                detail=f"Prescription details required for Schedule H1 drug: {product.name}")

        # Same patient-address requirement as create_bill — see the comment
        # there. This finalize-a-draft path is the other real entry point
        # that can turn an H1 item into a real sale.
        if is_finalizing_preview and is_sale_preview and product.drug_schedule == "H1" and (
                not bill_data.patient_address or not bill_data.patient_address.strip()):
            raise HTTPException(
                status_code=400,
                detail=f"Patient address required for Schedule H1 drug: {product.name}")

        quantity = item.get("quantity", 0)
        mrp_paise = int(item.get("unit_price", item.get("mrp", 0)) * 100)

        if is_finalizing_preview and is_sale_preview and mrp_paise > batch.mrp_paise:
            raise HTTPException(
                status_code=400,
                detail=(f"Selling price ₹{mrp_paise / 100:.2f} for {product.name} exceeds "
                        f"MRP ₹{batch.mrp_paise / 100:.2f} for batch {batch.batch_number}"))

        if (is_finalizing_preview and is_sale_preview and block_expired_stock
                and batch.expiry_date < today_for_expiry):
            raise HTTPException(
                status_code=400,
                detail=(f"{product.name} (batch {batch.batch_number}) expired on "
                        f"{batch.expiry_date.isoformat()} and cannot be sold."))
        if (is_finalizing_preview and is_sale_preview and not allow_near_expiry_sale
                and today_for_expiry <= batch.expiry_date
                < today_for_expiry + timedelta(days=near_expiry_days)):
            raise HTTPException(
                status_code=400,
                detail=(f"{product.name} (batch {batch.batch_number}) is near expiry "
                        f"({batch.expiry_date.isoformat()}) — near-expiry sales are "
                        f"disabled in Settings → Inventory."))

        disc_percent = item.get("disc_percent", item.get("discount_percent", 0))
        disc_paise = int(mrp_paise * quantity * disc_percent / 100)
        taxable_paise = mrp_paise * quantity - disc_paise
        gst_rate = item.get("gst_percent", bill_data.tax_rate or default_gst_rate)
        line_gst_paise = int(taxable_paise * gst_rate / 100)
        line_total_paise = taxable_paise + line_gst_paise
        line_cost_paise = batch.cost_price_paise * quantity

        bill_item = BillItemORM(
            bill_id=bid,
            product_id=product.id,
            batch_id=batch.id,
            product_name=item.get("product_name", item.get("medicine_name", product.name)),
            generic_name=product.generic_name,
            batch_number=batch.batch_number,
            expiry_date=batch.expiry_date,
            hsn_code=product.hsn_code,
            drug_schedule=product.drug_schedule,
            quantity=quantity,
            mrp_paise=mrp_paise,
            sale_price_paise=mrp_paise,
            cost_price_paise=batch.cost_price_paise,
            discount_percent=disc_percent,
            discount_paise=disc_paise,
            gst_rate=gst_rate,
            cgst_rate=gst_rate / 2,
            sgst_rate=gst_rate / 2,
            taxable_amount_paise=taxable_paise,
            cgst_paise=line_gst_paise // 2,
            sgst_paise=line_gst_paise - line_gst_paise // 2,
            gst_paise=line_gst_paise,
            line_total_paise=line_total_paise,
            line_cost_paise=line_cost_paise,
        )
        db.add(bill_item)
        item_orms.append((bill_item, batch, product))
        subtotal_paise += taxable_paise
        mrp_total_paise += mrp_paise * quantity
        item_discount_paise += disc_paise
        gst_paise += line_gst_paise
        cost_total_paise += line_cost_paise

    # Same gap as create_bill (see comment there): reject before generating
    # a real invoice number or touching stock, not after.
    if not item_orms:
        raise HTTPException(
            status_code=400,
            detail="Add at least one medicine to save this bill.")

    bill_discount_paise = int((bill_data.discount or 0) * 100)
    total_discount_paise = item_discount_paise + bill_discount_paise
    grand_total_paise = subtotal_paise + gst_paise - bill_discount_paise
    # Settings → Tax & GST "Round off amount" — see the identical fix in
    # create_bill.
    if round_off_amount:
        grand_total_paise = round(grand_total_paise / 100) * 100

    new_status = bill_data.status or "draft"
    is_finalizing = new_status == "paid" and bill.status == "draft"

    # Generate bill number on finalize
    if is_finalizing and (bill.bill_number == "Draft" or bill.bill_number.startswith("DRAFT-")):
        bill.bill_number = await _generate_bill_number(pharmacy_id, db)

    paid_paise = 0
    payment_splits: list[dict] = []
    resolved_payment_method = None
    if is_finalizing:
        resolved_payment_method, multi_paid_paise, payment_splits = _resolve_payment_splits(
            bill_data.payments, grand_total_paise)
        if resolved_payment_method:
            bill_data.payment_method = resolved_payment_method
            paid_paise = multi_paid_paise
        elif bill_data.payments:
            paid_paise = sum(int(p.get("amount", 0) * 100) for p in bill_data.payments)
        elif bill_data.payment_method:
            paid_paise = grand_total_paise
    elif was_finalized:
        # This is a correction to items/pricing on an already-settled bill,
        # not a new payment collection (that's Collect Payment, a separate
        # flow) — preserve exactly what cash was actually taken, and only
        # let the corrected total change how much is still owed.
        paid_paise = old_paid_paise
        bill_data.payment_method = old_payment_method

    balance_paise = max(0, grand_total_paise - paid_paise)

    # Sep 19, 2026 (Abinash, direct instruction): "Due"/partial-payment
    # bills are removed — same enforcement as create_bill. Catches both
    # ways this could happen: finalizing a draft that ends up underpaid, and
    # a same-day correction to an already-paid bill whose new total the
    # preserved paid amount no longer covers. A caller directly requesting
    # status="due" is rejected too, below.
    if (is_finalizing or was_finalized) and balance_paise > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This bill is short by ₹{balance_paise / 100:.2f} — "
                "a bill must be paid in full to finalize or correct."
            ),
        )
    if is_finalizing or was_finalized:
        new_status = "paid"
    if new_status == "due":
        raise HTTPException(
            status_code=400,
            detail="Due bills are no longer supported — a bill must be paid in full.")

    bill.subtotal_paise = subtotal_paise
    bill.mrp_total_paise = mrp_total_paise
    bill.item_discount_paise = item_discount_paise
    bill.bill_discount_paise = bill_discount_paise
    bill.total_discount_paise = total_discount_paise
    bill.taxable_amount_paise = subtotal_paise
    bill.total_cgst_paise = gst_paise // 2
    bill.total_sgst_paise = gst_paise - gst_paise // 2
    bill.total_gst_paise = gst_paise
    bill.grand_total_paise = grand_total_paise
    bill.amount_paid_paise = paid_paise
    bill.balance_paise = balance_paise
    bill.cost_total_paise = cost_total_paise
    bill.margin_paise = grand_total_paise - cost_total_paise
    bill.margin_percent = round(
        (bill.margin_paise /
         grand_total_paise *
         100) if grand_total_paise > 0 else 0,
        2)
    bill.customer_name = bill_data.customer_name or "Counter Sale"
    bill.customer_phone = bill_data.customer_mobile
    bill.doctor_name = bill_data.doctor_name
    bill.payment_method = bill_data.payment_method
    bill.status = new_status
    # Only touched when the client actually sends one — preserves the
    # original picked date on a save that doesn't touch it (e.g. an
    # auto-save while still typing), same guard pattern as every other
    # optional field here.
    if bill_data.bill_date:
        bill.bill_date = _resolve_bill_date(bill_data.bill_date)

    if payment_splits:
        await _save_payment_splits(bill.id, payment_splits, db)

    await db.flush()

    # Deduct stock if finalizing (draft -> paid) or if this is a same-day
    # correction to an already-finalized bill — was_finalized's old stock
    # effect was already reversed above, before the items were rebuilt.
    if is_finalizing or was_finalized:
        for bill_item, batch, product in item_orms:
            is_sale = bill_data.invoice_type == "SALE"
            await _deduct_stock_and_record(
                batch, product, bill_item.quantity, is_sale, bill.id, pharmacy_id, user_id, db)
            if is_sale:
                await _create_h1_entry(
                    product, batch, bill_item.quantity, bill, bill_item,
                    bill_data.doctor_name, bill_data.customer_name, pharmacy_id, user_id, db,
                    bill_data.patient_address, bill_data.patient_age)

    if is_finalizing:
        # Real, separate pre-existing gap closed here (necessary for this
        # feature to work correctly, not a gratuitous side fix): finalizing
        # a draft into a paid bill never wrote ANY audit_logs row at all —
        # create_bill logs a "create" action carrying paid_amount/
        # payment_method for Day-End Closing's cash breakdown to read
        # (see the comment on that call), but this, the *other* real path
        # that can produce a freshly-paid bill, logged nothing. Without
        # this, a draft finalized with a "Multi" split (or any payment
        # method) would be invisible to Day-End Closing, same root shape
        # as the Aug 22 MRP/stock/H1 miss Manifesto rule 11 is named after.
        await _record_audit(
            pharmacy_id, user_id, "create", "invoice", bill.id, None,
            {"bill_number": bill.bill_number, "invoice_type": bill.invoice_type, "status": new_status,
             "customer_name": bill.customer_name, "total_amount": grand_total_paise / 100,
             "paid_amount": paid_paise / 100, "due_amount": balance_paise / 100,
             "payment_method": bill.payment_method,
             "payment_splits": [{"method": s["method"], "amount": s["amount_paise"] / 100}
                                for s in payment_splits] if payment_splits else None},
            db, ip_address=_client_ip(request),
        )
    elif was_finalized:
        # Deliberately a different action name from "create"/"payment" —
        # Day-End Closing's cash breakdown (reports.py _day_end_breakdown)
        # only reads those two, so this edit is correctly invisible to it.
        # That's intentional, not a gap: paid_paise above is unchanged from
        # before the edit (nothing new was collected), so the real cash
        # attribution for the day is still accurate without this event —
        # only the corrected total/balance (read live off the Bill row)
        # needs to show up, which it already does.
        await _record_audit(
            pharmacy_id, user_id, "financial_edit", "invoice", bill.id,
            old_bill_snapshot,
            {"bill_number": bill.bill_number, "status": new_status,
             "customer_name": bill.customer_name, "total_amount": grand_total_paise / 100,
             "paid_amount": paid_paise / 100, "due_amount": balance_paise / 100,
             "payment_method": bill.payment_method},
            db, ip_address=_client_ip(request),
        )

    await db.flush()
    await db.refresh(bill)  # updated_at has onupdate=func.now() — see purchases.py

    items_result = await db.execute(select(BillItemORM).where(BillItemORM.bill_id == bid))
    normalized_splits = [{"method": s["method"], "amount": s["amount_paise"] / 100} for s in payment_splits]
    return _bill_response(bill, items_result.scalars().all(), normalized_splits)


@router.get("/bills")
async def get_bills(
    invoice_type: Optional[str] = None, status: Optional[str] = None,
    payment_method: Optional[str] = None,
    search: Optional[str] = None, from_date: Optional[str] = None, to_date: Optional[str] = None,
    page: int = 1, page_size: int = 50,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    query = select(BillORM).where(BillORM.pharmacy_id == pharmacy_id, BillORM.deleted_at.is_(None))
    if invoice_type:
        query = query.where(BillORM.invoice_type == invoice_type)
    if status:
        # 'parked' is stored as 'draft' in the DB (park saves a draft).
        # Match both so the Parked filter chip works correctly.
        if status == 'parked':
            query = query.where(BillORM.status.in_(['draft', 'parked']))
        else:
            query = query.where(BillORM.status == status)
    if payment_method:
        # Payment method filters must exclude drafts — a parked bill is not
        # a completed cash/upi sale. Only settled bills (paid/due) are shown.
        query = query.where(
            BillORM.payment_method.ilike(payment_method),
            BillORM.status.notin_(['draft', 'parked']),
        )
    if search:
        p = f"%{search}%"
        query = query.where(or_(
            BillORM.bill_number.ilike(p),
            BillORM.customer_name.ilike(p),
            BillORM.customer_phone.ilike(p),
        ))
    if from_date:
        query = query.where(BillORM.bill_date >= date.fromisoformat(from_date[:10]))
    if to_date:
        query = query.where(BillORM.bill_date <= date.fromisoformat(to_date[:10]))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(BillORM.created_at.desc()).offset(offset).limit(page_size))
    bills = result.scalars().all()

    return {
        "data": [_bill_list_response(b) for b in bills],
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total, "has_prev": page > 1,
        },
    }


@router.get("/bills/{bill_id}")
async def get_bill(bill_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    bill = await get_owned_or_404(
        db, BillORM, bill_id, uuid.UUID(current_user.pharmacy_id), not_found_detail="Bill not found")
    items_result = await db.execute(select(BillItemORM).where(BillItemORM.bill_id == bill.id))
    splits_result = await db.execute(
        select(BillPaymentSplitORM).where(BillPaymentSplitORM.bill_id == bill.id))
    splits = [{"method": s.payment_method, "amount": s.amount_paise / 100}
              for s in splits_result.scalars().all()]
    return _bill_response(bill, items_result.scalars().all(), splits)


@router.get("/bills/{bill_id}/pdf")
async def generate_bill_pdf(bill_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    from utils.bill_pdf import generate_bill_pdf_bytes

    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    # get_owned_or_404 scopes by pharmacy_id — without it, any logged-in
    # user from any pharmacy could download any other pharmacy's bill PDF
    # just by knowing (or guessing) a bill_id. This was a real, found and
    # fixed cross-tenant data leak here — but the same pattern still had to
    # be independently re-found and fixed across ~20 sibling endpoints
    # Sep 12, 2026 (RULE MISSES LOG), because this fix never got
    # generalized into a shared helper the first time. It has now.
    bill = await get_owned_or_404(db, BillORM, bill_id, pharmacy_id, not_found_detail="Bill not found")

    items_result = await db.execute(select(BillItemORM).where(BillItemORM.bill_id == bill.id))
    items = items_result.scalars().all()

    # For a "Multi" bill, bill.payment_method is the literal string
    # "multiple" — printed on its own that told the pharmacy nothing about
    # how the invoice was actually paid. Same fix as get_bill/_bill_response
    # (payment_splits) and PrintReceipt.jsx/BillTotals.jsx on the frontend —
    # found while checking every display surface of Bill.payment_method for
    # the Multi-payment feature (Manifesto rule 11).
    if bill.payment_method == "multiple":
        splits_result = await db.execute(
            select(BillPaymentSplitORM).where(BillPaymentSplitORM.bill_id == bill.id))
        payment_label = " + ".join(
            f"{s.payment_method.title()} Rs. {s.amount_paise / 100:.2f}"
            for s in splits_result.scalars().all())
    else:
        payment_label = (bill.payment_method or "").title()

    product_ids = [item.product_id for item in items]
    product_info: Dict[Any, Dict[str, str]] = {}
    if product_ids:
        prod_result = await db.execute(
            select(ProductORM.id, ProductORM.manufacturer, ProductORM.pack_size)
            .where(ProductORM.id.in_(product_ids))
        )
        product_info = {
            pid: {"manufacturer": manufacturer or "", "pack_size": pack_size or ""}
            for pid, manufacturer, pack_size in prod_result.all()
        }

    pharm_result = await db.execute(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
    pharmacy = pharm_result.scalar_one_or_none()
    ps_result = await db.execute(
        select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id)
    )
    ps = ps_result.scalar_one_or_none()

    # Reads Settings > Receipt & Print > Paper Size (ps.paper_size) and
    # picks a matching layout — used to be hardcoded to A4 regardless of
    # this setting, so an 80mm/58mm-thermal pharmacy always got a full A4
    # page on every download/reprint. See utils/bill_pdf.py.
    buffer = generate_bill_pdf_bytes(bill, items, product_info, pharmacy, ps, payment_label)

    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={bill.bill_number}.pdf"},
    )


# ── /payments ──────────────────────────────────────────────────────────────────

@router.post("/payments")
async def create_payment(payment_data: PaymentCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # permission-exempt: same pending app-wide Billing RBAC decision as create_bill above
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    bill = await get_owned_or_404(
        db, BillORM, payment_data.invoice_id, pharmacy_id, not_found_detail="Invoice not found")
    bid = bill.id

    if bill.status != "due":
        raise HTTPException(
            status_code=400,
            detail=f"This bill is '{bill.status}', not due — there is nothing to collect.")

    payment_paise = int(payment_data.amount * 100)
    if payment_paise <= 0:
        raise HTTPException(status_code=400, detail="Enter an amount greater than ₹0.")
    if payment_paise > bill.balance_paise:
        raise HTTPException(
            status_code=400,
            detail=(
                f"₹{payment_data.amount:.2f} is more than the ₹{bill.balance_paise / 100:.2f} "
                f"still owed on this bill."
            ),
        )

    new_paid = bill.amount_paid_paise + payment_paise
    new_balance = max(0, bill.grand_total_paise - new_paid)
    new_status = "paid" if new_balance <= 0 else "due"

    old_status = bill.status
    old_paid_amount = bill.amount_paid_paise / 100
    old_balance = bill.balance_paise / 100
    bill.amount_paid_paise = new_paid
    bill.balance_paise = new_balance
    bill.status = new_status
    bill.payment_method = payment_data.payment_method

    ip = _client_ip(request)
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "payment", "invoice", bid,
        {"paid_amount": old_paid_amount, "due_amount": old_balance, "status": old_status},
        {"amount": payment_data.amount,
         "payment_method": payment_data.payment_method,
         "new_status": new_status},
        db, ip_address=ip,
    )

    if old_status != new_status:
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "status_change", "invoice", bid,
            {"status": old_status, "due_amount": (
                bill.grand_total_paise - bill.amount_paid_paise + payment_paise) / 100},
            {"status": new_status, "due_amount": new_balance / 100},
            db, ip_address=ip,
        )

    await db.flush()

    return {
        "id": str(uuid.uuid4()),
        "invoice_id": str(bid),
        "amount": payment_data.amount,
        "payment_method": payment_data.payment_method,
        "reference_number": payment_data.reference_number,
        "notes": payment_data.notes,
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/payments")
async def get_payments(invoice_id: Optional[str] = None, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    if not invoice_id:
        return []
    try:
        bill = await get_owned_or_404(
            db, BillORM, invoice_id, uuid.UUID(current_user.pharmacy_id))
    except HTTPException:
        return []  # matches this endpoint's existing "not found -> []" contract
    bid = bill.id
    # Return payment info from the bill itself
    if bill.amount_paid_paise > 0:
        return [{
            "id": str(uuid.uuid4()),
            "invoice_id": str(bid),
            "amount": bill.amount_paid_paise / 100,
            "payment_method": bill.payment_method or "cash",
            "created_at": bill.created_at.isoformat() if bill.created_at else None,
        }]
    return []


# ── /refunds ───────────────────────────────────────────────────────────────────

@router.post("/refunds")
async def create_refund(refund_data: RefundCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # permission-exempt: same pending app-wide Billing RBAC decision as create_bill above
    bill = await get_owned_or_404(
        db, BillORM, refund_data.return_invoice_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Return invoice not found")
    bid = bill.id
    if bill.invoice_type != "SALES_RETURN":
        raise HTTPException(status_code=400, detail="Invoice is not a sales return")

    old_status = bill.status
    bill.status = "refunded"

    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id),
        "create", "refund", bid, {"status": old_status},
        {"amount": refund_data.amount,
         "refund_method": refund_data.refund_method,
         "reason": refund_data.reason},
        db, ip_address=_client_ip(request),
    )
    await db.flush()

    return {
        "id": str(uuid.uuid4()),
        "return_invoice_id": str(bid),
        "original_invoice_id": refund_data.original_invoice_id,
        "amount": refund_data.amount,
        "refund_method": refund_data.refund_method,
        "reference_number": refund_data.reference_number,
        "reason": refund_data.reason,
        "notes": refund_data.notes,
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/refunds")
async def get_refunds(
        return_invoice_id: Optional[str] = None,
        original_invoice_id: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    # Refunds are tracked via bill status and audit logs
    if not return_invoice_id:
        return []
    try:
        bill = await get_owned_or_404(
            db, BillORM, return_invoice_id, uuid.UUID(current_user.pharmacy_id))
    except HTTPException:
        return []  # matches this endpoint's existing "not found -> []" contract
    bid = bill.id
    if bill.status != "refunded":
        return []
    return [{
        "id": str(uuid.uuid4()),
        "return_invoice_id": str(bid),
        "amount": bill.grand_total_paise / 100,
        "refund_method": bill.payment_method or "cash",
        "created_at": bill.updated_at.isoformat() if bill.updated_at else None,
    }]


# ── /audit-logs ────────────────────────────────────────────────────────────────

async def _resolve_user_names(user_ids: set[uuid.UUID], db: AsyncSession) -> dict[uuid.UUID, str]:
    # Both audit-log endpoints below only ever returned the raw performed_by
    # UUID — AuditLog.jsx rendered it truncated ("a3f92c1e…") instead of a
    # real name, since it never had one to show. One batched lookup here
    # instead of a lookup per row.
    if not user_ids:
        return {}
    result = await db.execute(select(UserORM.id, UserORM.name).where(UserORM.id.in_(user_ids)))
    return {uid: name for uid, name in result.all()}


@router.get("/audit-logs")
async def get_audit_logs(
    entity_type: Optional[str] = None, entity_id: Optional[str] = None,
    action: Optional[str] = None,
    page: int = 1, page_size: int = 50,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    # Found Sep 12, 2026: no permission gate existed here at all — any
    # logged-in role, cashier included, could read the full action history
    # of every user in the pharmacy. Reuses reports:view since Audit Log is
    # grouped under "Reports & Compliance" and this preserves the same
    # admin/manager-only shape as Schedule H1's own gate.
    if not await has_permission(current_user, "reports:view", db):
        raise HTTPException(
            status_code=403, detail="Your role does not have permission to view the audit log")
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    query = select(AuditLog).where(AuditLog.pharmacy_id == pharmacy_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == uuid.UUID(entity_id))
    if action:
        query = query.where(AuditLog.action == action)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
    logs = result.scalars().all()
    names_by_id = await _resolve_user_names({log.user_id for log in logs if log.user_id}, db)

    return {
        "data": [{
            "id": str(log.id),
            "entity_type": log.entity_type,
            "entity_id": str(log.entity_id) if log.entity_id else None,
            "action": log.action,
            "old_value": log.old_values,
            "new_value": log.new_values,
            "ip_address": log.ip_address,
            "performed_by": str(log.user_id) if log.user_id else None,
            "performed_by_name": names_by_id.get(log.user_id) if log.user_id else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        } for log in logs],
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "has_next": page * page_size < total, "has_prev": page > 1,
        },
    }


@router.get("/audit-logs/entity/{entity_type}/{entity_id}")
async def get_entity_audit_trail(entity_type: str, entity_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # Found Sep 12, 2026 alongside the multi-tenancy fix pass: this had no
    # pharmacy_id filter at all — any logged-in user from any pharmacy could
    # pull another pharmacy's full audit trail (old/new values, including
    # customer names and totals) for any entity_id, just by knowing or
    # guessing one. Missed by scripts/check_tenant_isolation.py's static
    # check because that check only flags a bare `Model.id ==` — this
    # filters on `entity_id`, a different attribute name, on a *list* query
    # rather than a single-row by-id lookup, so get_owned_or_404 doesn't fit
    # here either. See docs/15_ROADMAP.md RULE MISSES LOG.
    if not await has_permission(current_user, "reports:view", db):
        raise HTTPException(
            status_code=403, detail="Your role does not have permission to view the audit log")
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.pharmacy_id == pharmacy_id, AuditLog.entity_type == entity_type,
               AuditLog.entity_id == uuid.UUID(entity_id))
        .order_by(AuditLog.created_at)
    )
    logs = result.scalars().all()
    names_by_id = await _resolve_user_names({log.user_id for log in logs if log.user_id}, db)

    return [{
        "id": str(log.id),
        "entity_type": log.entity_type,
        "entity_id": str(log.entity_id) if log.entity_id else None,
        "action": log.action,
        "old_value": log.old_values,
        "new_value": log.new_values,
        "ip_address": log.ip_address,
        "performed_by": str(log.user_id) if log.user_id else None,
        "performed_by_name": names_by_id.get(log.user_id) if log.user_id else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    } for log in logs]
