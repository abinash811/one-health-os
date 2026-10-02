from __future__ import annotations

import base64
import io
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.products import Product as ProductORM, StockBatch as BatchORM, StockMovement as MovementORM
from models.purchases import (
    Purchase as PurchaseORM,
    PurchaseItem as PurchaseItemORM,
    PurchasePayment as PurchasePaymentORM,
)
from models.suppliers import Supplier as SupplierORM
from models.users import AuditLog
from routers.auth_helpers import (
    User, get_current_user, get_owned_or_404, has_permission, require_admin_or_super,
    resolve_store_override_for_write,
)

router = APIRouter(prefix="/api", tags=["purchases"])


# ── Pydantic request models ──────────────────────────────────────────────────

class PurchaseItemCreate(BaseModel):
    product_sku: str
    product_name: str
    batch_no: Optional[str] = None
    expiry_date: Optional[str] = None
    qty_packs: Optional[int] = None
    qty_units: int
    # None = physically received exactly what was ordered/invoiced (the
    # common case — no extra entry needed). Set only when the delivery was
    # short or in excess of qty_units; drives real stock added, while
    # qty_units alone still drives cost/GST/what's owed to the supplier
    # (that's what the invoice says, short delivery or not).
    received_qty_units: Optional[int] = None
    free_qty_units: Optional[int] = 0
    cost_price_per_unit: float
    mrp_per_unit: float
    gst_percent: float = 5.0
    batch_priority: str = "LIFA"


class PurchaseCreate(BaseModel):
    supplier_id: str
    purchase_date: str
    # Optional — set only when an HQ-authorized person places this order for
    # a DIFFERENT store than the one they're currently active in (the
    # picker on the New Purchase screen, docs/26_MULTI_CHAIN_SCOPE.md
    # Section 3 #3). Omitted/blank = today's behavior, unchanged: the
    # purchase belongs to the caller's own currently active store.
    pharmacy_id: Optional[str] = None
    due_date: Optional[str] = None
    supplier_invoice_no: Optional[str] = None
    supplier_invoice_date: Optional[str] = None
    order_type: str = "direct"
    with_gst: bool = True
    purchase_on: str = "credit"
    items: List[PurchaseItemCreate]
    note: Optional[str] = None
    status: Optional[str] = "draft"
    payment_status: str = "unpaid"
    # Match InvoiceBreakdownModal.jsx's own net-amount formula exactly:
    # net = bill_amount - total_discount + cess - adjusted_cn + tcs
    #       + extra_charges + adjustment_amount, rounded to the nearest rupee.
    total_discount: float = 0
    cess: float = 0
    adjusted_cn: float = 0
    tcs: float = 0
    extra_charges: float = 0
    adjustment_amount: float = 0
    invoice_attachment_data: Optional[str] = None
    invoice_attachment_name: Optional[str] = None


class PurchasePaymentRequest(BaseModel):
    amount: float
    payment_method: str = "cash"
    payment_date: Optional[str] = None
    reference_no: Optional[str] = None
    notes: Optional[str] = None


class PurchaseItemCorrection(BaseModel):
    item_id: str
    mrp_per_unit: Optional[float] = None
    cost_price_per_unit: Optional[float] = None
    batch_no: Optional[str] = None
    expiry_date: Optional[str] = None


class PurchaseCorrectionRequest(BaseModel):
    """UC-P09 (docs/23_PURCHASES_ACCEPTANCE_SPEC.md) — deliberately
    narrower than a full re-edit. Quantity is NOT correctable here: a
    confirmed purchase's stock may already have been sold or returned
    against, so retroactively changing quantity_ordered/free_qty risks
    silently inventing or destroying stock that no longer matches what
    was physically received. A genuine quantity mistake goes through the
    existing purchase-return flow instead. What IS correctable is exactly
    the class of typo real pharmacists actually hit: wrong MRP, wrong
    cost price/PTR, wrong batch number, wrong expiry date, wrong invoice
    number/date/notes."""
    reason: str
    supplier_invoice_number: Optional[str] = None
    supplier_invoice_date: Optional[str] = None
    notes: Optional[str] = None
    items: Optional[List[PurchaseItemCorrection]] = None


class PaymentReversalRequest(BaseModel):
    reason: str


class BillImportRequest(BaseModel):
    filename: str
    file_data: str  # base64, same convention as invoice_attachment_data — may carry a data: URL prefix


# ── helpers ───────────────────────────────────────────────────────────────────

# One-click distributor bill import (Suppliers v3, Pharmasoft-named gap) —
# a fixed-template Excel/CSV import, not free-form parsing of an arbitrary
# distributor invoice layout. Column names are matched case-insensitively
# against these aliases so a pharmacist's own header wording still works.
_BILL_IMPORT_COLUMN_ALIASES = {
    "product_sku":  ["product sku", "sku", "product code"],
    "product_name": ["product name", "product", "item name", "medicine name", "item"],
    "batch_no":     ["batch no", "batch number", "batch", "batch no."],
    "expiry":       ["expiry", "expiry date", "expiry (mm/yyyy)", "exp date", "exp"],
    "quantity":     ["quantity", "qty", "quantity (units)", "qty (units)", "units"],
    "cost_price":   ["cost price", "cost price (per unit)", "rate", "purchase rate", "ptr", "cost"],
    "mrp":          ["mrp", "mrp (per unit)"],
    "gst_percent":  ["gst %", "gst", "gst percent", "tax %", "gst rate"],
}
_BILL_IMPORT_REQUIRED_FIELDS = ["batch_no", "quantity", "cost_price", "mrp"]
_BILL_IMPORT_MAX_ROWS = 500
_BILL_IMPORT_MAX_BYTES = 5 * 1024 * 1024


def _map_bill_import_columns(columns) -> dict:
    normalized = {str(c).strip().lower(): c for c in columns}
    mapped = {}
    for field, aliases in _BILL_IMPORT_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapped[field] = normalized[alias]
                break
    return mapped


def _parse_expiry_to_mmyy(raw) -> Optional[str]:
    """Converts whatever expiry format a distributor's bill uses into the
    MM/YY string PurchaseItemsTable's own expiry field already expects
    (see expiryToISO in buildPurchasePayload.js) — full dates, MM/YYYY,
    and MM/YY are all accepted since real bills vary."""
    if raw is None:
        return None
    if isinstance(raw, (pd.Timestamp, datetime, date)):
        return f"{raw.month:02d}/{str(raw.year)[2:]}"

    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None

    m = re.match(r"^(\d{1,2})[/\-](\d{4})$", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1)):02d}/{m.group(2)[2:]}"

    m = re.match(r"^(\d{1,2})[/\-](\d{2})$", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1)):02d}/{m.group(2)}"

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(s, fmt)
            return f"{d.month:02d}/{str(d.year)[2:]}"
        except ValueError:
            continue
    return None


def _parse_bill_import_row(row, col_map: dict, by_sku: dict, by_name: dict) -> tuple[dict, list[str]]:
    def get(field):
        col = col_map.get(field)
        if col is None or col not in row.index:
            return None
        value = row[col]
        return None if pd.isna(value) else value

    sku_raw = get("product_sku")
    name_raw = get("product_name")
    sku = str(sku_raw).strip() if sku_raw is not None else None
    name = str(name_raw).strip() if name_raw is not None else None
    batch_no = get("batch_no")
    quantity = get("quantity")
    cost_price = get("cost_price")
    mrp = get("mrp")
    gst_percent = get("gst_percent")
    expiry_raw = get("expiry")

    if not batch_no:
        raise ValueError("missing batch number")
    if quantity is None or cost_price is None or mrp is None:
        raise ValueError("missing quantity, cost price, or MRP")

    matched = None
    if sku and sku.lower() in by_sku:
        matched = by_sku[sku.lower()]
    elif name and name.lower() in by_name:
        matched = by_name[name.lower()]

    warnings: list[str] = []
    if not matched:
        warnings.append("Product not found in inventory — select the correct product manually")

    expiry_mmyy = _parse_expiry_to_mmyy(expiry_raw)
    if not expiry_mmyy:
        warnings.append("Could not read the expiry date — enter it manually")

    try:
        qty_units = int(float(quantity))
        cost_price_per_unit = float(cost_price)
        mrp_per_unit = float(mrp)
    except (TypeError, ValueError):
        raise ValueError("quantity, cost price, and MRP must be numbers")

    item = {
        "product_sku": matched.sku if matched else (sku or ""),
        "product_name": matched.name if matched else (name or sku or "Unknown product"),
        "matched_product": matched is not None,
        "batch_no": str(batch_no).strip(),
        "expiry_mmyy": expiry_mmyy or "",
        "qty_units": qty_units,
        "cost_price_per_unit": cost_price_per_unit,
        "mrp_per_unit": mrp_per_unit,
        "gst_percent": (float(gst_percent) if gst_percent is not None
                        else (float(matched.gst_rate) if matched else 5.0)),
    }
    return item, warnings


async def _generate_purchase_number(pharmacy_id: uuid.UUID, db: AsyncSession) -> str:
    # MAX() on the numeric suffix, cast in SQL — not ORDER BY ... DESC LIMIT 1
    # on the padded string column. The string-sort version silently produced
    # a duplicate the moment the suffix crossed a zero-padding width (e.g.
    # "PUR-2026-9999" sorts AFTER "PUR-2026-10000" lexicographically), which
    # 500'd every purchase creation for that pharmacy from then on — found
    # Sep 19, 2026 via a live IntegrityError once a dev DB crossed 10,000.
    current_year = datetime.now(timezone.utc).year
    prefix = f"PUR-{current_year}-"
    result = await db.execute(
        select(func.max(cast(func.split_part(PurchaseORM.purchase_number, "-", 3), Integer)))
        .where(PurchaseORM.pharmacy_id == pharmacy_id, PurchaseORM.purchase_number.like(f"{prefix}%"))
    )
    last_num = result.scalar_one_or_none()
    new_num = (last_num or 0) + 1
    return f"{prefix}{new_num:04d}"


async def _get_product_skus(items: list[PurchaseItemORM], db: AsyncSession) -> dict:
    """PurchaseItem only stores product_id (its real FK) — product_sku is a
    request/response-only convenience the frontend's edit flow round-trips
    unchanged on save. Never populating it here meant every edit of an
    existing draft item 404'd on save (_get_product_by_sku(pharmacy_id, "",
    db) — the blank string the response always used to carry back)."""
    product_ids = {i.product_id for i in items}
    if not product_ids:
        return {}
    result = await db.execute(select(ProductORM.id, ProductORM.sku).where(ProductORM.id.in_(product_ids)))
    return {pid: sku for pid, sku in result.all()}


async def _purchase_response(p: PurchaseORM, items: list[PurchaseItemORM], db: AsyncSession) -> dict:
    product_skus = await _get_product_skus(items, db)
    return {
        "id": str(p.id),
        "purchase_number": p.purchase_number,
        "supplier_id": str(p.supplier_id),
        "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
        "due_date": p.due_date.isoformat() if p.due_date else None,
        "supplier_invoice_no": p.supplier_invoice_number,
        "supplier_invoice_date": p.supplier_invoice_date.isoformat() if p.supplier_invoice_date else None,
        "status": p.status,
        "payment_status": p.payment_status,
        "order_type": p.order_type,
        "with_gst": p.with_gst,
        "purchase_on": p.purchase_on,
        "subtotal": p.subtotal_paise / 100,
        "tax_value": p.total_gst_paise / 100,
        "total_discount": p.total_discount_paise / 100,
        "cess": p.cess_paise / 100,
        "adjusted_cn": p.adjusted_cn_paise / 100,
        "tcs": p.tcs_paise / 100,
        "extra_charges": p.extra_charges_paise / 100,
        "adjustment_amount": p.adjustment_amount_paise / 100,
        # grand_total_paise is rounded to the nearest rupee at create/update
        # time (see create_purchase/update_purchase) — round_off is whatever
        # remains after every other explicit term, not a fake constant.
        "round_off": (p.grand_total_paise - (
            p.subtotal_paise + p.total_gst_paise - p.total_discount_paise + p.cess_paise
            - p.adjusted_cn_paise + p.tcs_paise + p.extra_charges_paise + p.adjustment_amount_paise
        )) / 100,
        "total_value": p.grand_total_paise / 100,
        "amount_paid": p.amount_paid_paise / 100,
        # Set by callers that already have a payments row to look up
        # (get_purchase, mark_purchase_paid) — stays None for a purchase
        # that has never been paid, or hasn't been looked up with its
        # payments (create_purchase/update_purchase, where a brand-new
        # purchase can't have a payment yet).
        "last_payment_date": None,
        "invoice_attachment_data": p.invoice_attachment_data,
        "invoice_attachment_name": p.invoice_attachment_name,
        "note": p.notes,
        "items": [_purchase_item_response(i, product_skus) for i in items],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _purchase_item_response(i: PurchaseItemORM, product_skus: Optional[dict] = None) -> dict:
    return {
        "id": str(i.id),
        "product_sku": (product_skus or {}).get(i.product_id, ""),
        "product_name": i.product_name,
        "batch_no": i.batch_number,
        "expiry_date": i.expiry_date.isoformat() if i.expiry_date else None,
        "qty_units": i.quantity_ordered,
        "free_qty_units": i.free_qty_units,
        "cost_price_per_unit": i.cost_price_paise / 100,
        "mrp_per_unit": i.mrp_paise / 100,
        # Stored at confirm time (from the product's own units_per_pack) but
        # never returned before Sep 24, 2026 — the frontend's Pack/Unit
        # toggle needs it to show/edit a draft's real pack size when it's
        # loaded back for editing.
        "units_per_pack": i.units_per_pack,
        "gst_percent": float(i.gst_rate),
        "line_total": i.line_total_paise / 100,
        "received_qty_units": i.quantity_received,
    }


def _purchase_list_response(p: PurchaseORM, supplier_name: str = "") -> dict:
    return {
        "id": str(p.id),
        "purchase_number": p.purchase_number,
        "supplier_id": str(p.supplier_id),
        "supplier_name": supplier_name,
        "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
        "due_date": p.due_date.isoformat() if p.due_date else None,
        "supplier_invoice_no": p.supplier_invoice_number,
        "status": p.status,
        "payment_status": p.payment_status,
        "purchase_on": p.purchase_on,
        "subtotal": p.subtotal_paise / 100,
        "tax_value": p.total_gst_paise / 100,
        "total_value": p.grand_total_paise / 100,
        "amount_paid": p.amount_paid_paise / 100,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _get_last_payment_date(purchase_id: uuid.UUID, db: AsyncSession) -> Optional[str]:
    result = await db.execute(
        select(PurchasePaymentORM.payment_date)
        .where(PurchasePaymentORM.purchase_id == purchase_id,
               PurchasePaymentORM.reversed_at.is_(None))
        .order_by(PurchasePaymentORM.payment_date.desc(), PurchasePaymentORM.created_at.desc())
        .limit(1)
    )
    last_date = result.scalar_one_or_none()
    return last_date.isoformat() if last_date else None


async def _get_product_by_sku(pharmacy_id: uuid.UUID, sku: str, db: AsyncSession) -> ProductORM:
    result = await db.execute(
        select(ProductORM).where(ProductORM.pharmacy_id == pharmacy_id, ProductORM.sku == sku)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {sku} not found")
    return product


INVOICE_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024  # 5MB decoded
INVOICE_ATTACHMENT_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def _validate_invoice_attachment(data_url: str) -> None:
    """data_url is a data: URL (e.g. "data:application/pdf;base64,JVBERi0..."),
    same client-side-base64 shape LogoUpload.tsx already produces — no
    backend upload endpoint or file storage exists anywhere in this
    codebase to justify standing one up for a single per-purchase file."""
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise HTTPException(status_code=400, detail="Invalid invoice attachment format")

    header, _, b64_payload = data_url.partition(";base64,")
    mime_type = header[len("data:"):]
    if mime_type not in INVOICE_ATTACHMENT_ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice attachment must be an image or PDF, got '{mime_type}'")

    try:
        decoded = base64.b64decode(b64_payload, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invoice attachment is not valid base64 data")

    if len(decoded) > INVOICE_ATTACHMENT_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice attachment must be under {INVOICE_ATTACHMENT_MAX_BYTES // (1024 * 1024)}MB")


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    # old_values/ip_address were defined on the AuditLog schema since the
    # app's start but this helper never accepted either — every row's
    # old_value/ip_address was permanently NULL (docs/23_PURCHASES_
    # ACCEPTANCE_SPEC.md finding #16). Fixed Sep 12, 2026 alongside the
    # same gap in billing.py/purchase_returns.py's own local copies of
    # this helper.
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _require_purchases_permission(current_user: User, action: str, db: AsyncSession) -> None:
    """The `roles` table + has_permission() (auth_helpers.py) have existed
    since the app's seed data (seed_admin.py's ROLE_PERMISSIONS — manager
    gets purchases view/create/edit, inventory_staff gets view/create,
    cashier gets none) but were never actually called from any endpoint
    anywhere in the app. Wired in here for Purchases/Purchase Returns
    only — every other module remains unenforced for now, a deliberate,
    scoped first step rather than a sweeping app-wide rollout."""
    if not await has_permission(current_user, f"purchases:{action}", db):
        raise HTTPException(
            status_code=403,
            detail=f"Your role does not have permission to {action} purchases")


async def _create_stock_for_items(
    purchase: PurchaseORM, items: list[PurchaseItemORM],
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession,
    received_overrides: Optional[dict[int, int]] = None,
) -> None:
    """Create stock batches and movements when a purchase is confirmed.

    StockBatch.quantity_on_hand is in real units everywhere it's written
    (billing.py, purchase_returns.py, sales_returns.py, batches.py/adjust)
    — item.quantity_ordered is also in units (PurchaseItemCreate.qty_units),
    so no conversion happens here. Before Sep 11, 2026 (migration
    a343c922f896) this floor-divided by units_per_pack to get a pack count
    — found live: ordering 25 units of a 10-unit-pack product created a
    batch with quantity_on_hand=2 (packs), silently losing 5 of the 25
    units actually paid for and received. See docs/15_ROADMAP.md RULE
    MISSES LOG.

    free_qty_units (bonus units received but not billed) are real
    physical stock and go into quantity_received/quantity_on_hand same
    as paid units — but were never included in taxable_amount_paise/
    line_total_paise (see create_purchase/update_purchase), so no tax
    or cost-price change is needed here to account for them correctly.

    received_overrides (item index -> real received units, paid only, not
    counting free_qty_units) is set only when the delivery didn't match
    what was ordered/invoiced — a short or excess supply (Sep 25, 2026).
    quantity_ordered still drives cost/GST/what's owed to the supplier
    unchanged; only the real stock added, and item.quantity_received
    itself, follow the override. Falls back to quantity_ordered when no
    override is given, so a purchase with no discrepancy behaves exactly
    as before this existed.
    """
    for idx, item in enumerate(items):
        # MRP=0 (or negative) is accepted by PurchaseItemCreate's plain
        # `float` type and was never checked before the batch this MRP
        # gets stamped onto is actually created — a purchase confirmed
        # with an unfilled MRP field silently produced stock nobody could
        # bill correctly. Gated here (confirm-time only, not draft
        # save/update) so an in-progress draft can still be saved with
        # the field left blank, same as qty/PTR/batch/expiry already are.
        if item.mrp_paise <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"MRP for {item.product_name} must be greater than ₹0 to confirm this purchase")

        paid_units = item.quantity_ordered or 0
        if received_overrides and idx in received_overrides:
            paid_units = received_overrides[idx]
            if paid_units < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Received quantity for {item.product_name} cannot be negative")
        total_units = paid_units + (item.free_qty_units or 0)
        # Was `f"PUR-{purchase.purchase_number[:8]}"` — purchase_number's
        # format is "PUR-YYYY-NNNN", so the first 8 characters are always
        # just "PUR-YYYY", identical for every purchase confirmed in the
        # same year. That made every no-batch-number confirmation of the
        # same product collide on the exact same fallback string —
        # rejected as "already exists" for two genuinely different
        # purchases, and even for two different line items of the same
        # product within one purchase. Using the full (real, unique)
        # purchase_number plus this item's position fixes both: this is
        # also the actual root cause of the documented "genuine double-
        # submit with no batch number" bug — two concurrent submits get
        # two different real purchase_numbers, so their fallback batch
        # numbers now genuinely differ too, the way the guard below
        # always assumed they would.
        batch_number = item.batch_number or f"{purchase.purchase_number}-{idx}"

        # Same duplicate check POST /stock/batches already enforces — this
        # confirm path had none, so two purchases entering the same
        # real-world batch number for the same product silently created
        # two independent StockBatch rows instead of one. Scoped to active
        # batches so a number can be reused once the original is written
        # off/deactivated — matches the DB constraint added below.
        existing = await db.execute(
            select(BatchORM).where(
                BatchORM.product_id == item.product_id,
                BatchORM.batch_number == batch_number,
                BatchORM.is_active.is_(True),
            )
        )
        duplicate_batch_detail = (
            f"A batch numbered '{batch_number}' already exists for this product — "
            f"receive additional stock against the existing batch instead of "
            f"confirming a purchase with the same batch number again.")
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=duplicate_batch_detail)

        batch = BatchORM(
            pharmacy_id=pharmacy_id,
            product_id=item.product_id,
            batch_number=batch_number,
            expiry_date=item.expiry_date or date.today() + timedelta(days=365),
            mrp_paise=item.mrp_paise,
            cost_price_paise=item.cost_price_paise,
            quantity_received=total_units,
            quantity_on_hand=total_units,
        )
        db.add(batch)
        try:
            await db.flush()
        except IntegrityError:
            # The SELECT above is not atomic with this INSERT — two
            # near-simultaneous confirms of the same purchase (double-
            # click, two browser tabs) could both pass it before either
            # insert landed, each creating a full stock batch and
            # silently doubling stock. `uq_batches_product_batchnumber_
            # active` (migration 29481ee67a4b) makes the DB itself the
            # final word; this is what actually catches the race the
            # in-app check above cannot.
            raise HTTPException(status_code=400, detail=duplicate_batch_detail)

        # Link batch to purchase item — also backfill batch_number when a
        # fallback was generated, so the purchase item (and its API
        # response) reflects the real batch identifier actually used
        # instead of staying blank.
        item.batch_id = batch.id
        item.batch_number = batch_number
        # Was left at its create-time default (0) forever before this —
        # _purchase_item_response's "received_qty_units" field existed but
        # always reported 0, regardless of what actually got confirmed.
        item.quantity_received = total_units

        db.add(MovementORM(
            pharmacy_id=pharmacy_id, product_id=item.product_id, batch_id=batch.id,
            movement_type="purchase", quantity=total_units,
            quantity_before=0, quantity_after=total_units,
            reference_type="purchase", reference_id=purchase.id,
            user_id=user_id, notes=f"Purchase {purchase.purchase_number}",
        ))


# ── /purchases ─────────────────────────────────────────────────────────────────

@router.post("/purchases/import-bill")
async def import_purchase_bill(
        payload: BillImportRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """One-click distributor bill import (Suppliers v3, named Pharmasoft
    gap) — a pharmacist uploads a distributor's Excel/CSV bill against a
    fixed column template instead of retyping every line item by hand.
    Returns candidate items in the exact shape PurchaseNew's own item rows
    use (product_sku/product_name/batch_no/expiry_mmyy/qty_units/
    cost_price_per_unit/mrp_per_unit/gst_percent) so the frontend can load
    them straight into the existing, already-tested purchase-creation
    flow for review and submission — this endpoint only parses, it never
    creates a purchase itself."""
    # audit-exempt: read-only parse/preview — writes no DB row, creates no
    # purchase; the real purchase this feeds into is audited by create_purchase
    await _require_purchases_permission(current_user, "create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    ext = Path(payload.filename).suffix.lower()
    if ext not in {".xlsx", ".xls", ".csv"}:
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls, or .csv files are supported")

    raw_b64 = payload.file_data.split(",", 1)[-1]
    try:
        content = base64.b64decode(raw_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode the uploaded file")

    if len(content) > _BILL_IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {_BILL_IMPORT_MAX_BYTES // (1024 * 1024)}MB)")

    try:
        df = pd.read_csv(io.BytesIO(content)) if ext == ".csv" else pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read the file — is it a valid {ext} file? ({e})")

    if df.empty:
        raise HTTPException(status_code=400, detail="The file has no data rows")
    if len(df) > _BILL_IMPORT_MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"File has too many rows (max {_BILL_IMPORT_MAX_ROWS}) — split into smaller files")

    col_map = _map_bill_import_columns(df.columns)
    missing = [f for f in _BILL_IMPORT_REQUIRED_FIELDS if f not in col_map]
    if "product_sku" not in col_map and "product_name" not in col_map:
        missing.append("Product SKU or Product Name")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(f"Missing required column(s): {', '.join(missing)}. Expected columns like "
                    "Product Name/SKU, Batch No, Expiry, Quantity, Cost Price, MRP."))

    products_result = await db.execute(
        select(ProductORM).where(ProductORM.pharmacy_id == pharmacy_id, ProductORM.deleted_at.is_(None)))
    products = products_result.scalars().all()
    by_sku = {p.sku.lower(): p for p in products if p.sku}
    by_name = {p.name.lower(): p for p in products if p.name}

    items, errors = [], []
    for idx, row in df.iterrows():
        row_num = idx + 2  # header is row 1
        try:
            item, warnings = _parse_bill_import_row(row, col_map, by_sku, by_name)
        except ValueError as e:
            errors.append({"row": row_num, "message": str(e)})
            continue
        item["row"] = row_num
        item["warnings"] = warnings
        items.append(item)

    return {"items": items, "errors": errors}


@router.get("/purchases")
async def get_purchases(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    supplier_id: Optional[str] = None, status: Optional[str] = None,
    purchase_on: Optional[str] = None, payment_status: Optional[str] = None,
    search: Optional[str] = None, page: int = 1, page_size: int = 50,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    query = select(PurchaseORM).where(
        PurchaseORM.pharmacy_id == pharmacy_id,
        PurchaseORM.deleted_at.is_(None))
    if from_date:
        query = query.where(PurchaseORM.purchase_date >= date.fromisoformat(from_date[:10]))
    if to_date:
        query = query.where(PurchaseORM.purchase_date <= date.fromisoformat(to_date[:10]))
    if supplier_id:
        query = query.where(PurchaseORM.supplier_id == uuid.UUID(supplier_id))
    if status:
        query = query.where(PurchaseORM.status == status)
    if purchase_on:
        query = query.where(PurchaseORM.purchase_on == purchase_on)
    if payment_status == "unpaid":
        # "Due" filter: anything still owed money on — unpaid or partially
        # paid — excluding drafts, which carry no financial obligation yet.
        query = query.where(
            PurchaseORM.status != "draft",
            PurchaseORM.payment_status.in_(["unpaid", "partial"]))
    elif payment_status:
        query = query.where(PurchaseORM.payment_status == payment_status)
    if search:
        p = f"%{search}%"
        matching_supplier_ids = select(SupplierORM.id).where(
            SupplierORM.pharmacy_id == pharmacy_id, SupplierORM.name.ilike(p))
        query = query.where(or_(
            PurchaseORM.purchase_number.ilike(p),
            PurchaseORM.supplier_invoice_number.ilike(p),
            PurchaseORM.supplier_id.in_(matching_supplier_ids),
        ))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(PurchaseORM.purchase_date.desc()).offset(offset).limit(page_size))
    purchases = result.scalars().all()

    # Gather supplier names
    supplier_ids = {p.supplier_id for p in purchases}
    sup_result = await db.execute(select(SupplierORM).where(SupplierORM.id.in_(supplier_ids))) if supplier_ids else None
    supplier_map = {s.id: s.name for s in sup_result.scalars().all()} if sup_result else {}

    data = [_purchase_list_response(p, supplier_map.get(p.supplier_id, "")) for p in purchases]

    return {
        "data": data,
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total, "has_prev": page > 1,
        },
    }


@router.post("/purchases")
async def create_purchase(purchase_data: PurchaseCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    pharmacy_id = await resolve_store_override_for_write(
        current_user, purchase_data.pharmacy_id, "purchases:create", db)
    if purchase_data.invoice_attachment_data:
        _validate_invoice_attachment(purchase_data.invoice_attachment_data)
    supplier_id = uuid.UUID(purchase_data.supplier_id)

    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, pharmacy_id, not_found_detail="Supplier not found")

    purchase_number = await _generate_purchase_number(pharmacy_id, db)

    # Calculate totals and build items
    subtotal_paise = 0
    tax_paise = 0
    item_orms: list[PurchaseItemORM] = []

    for item_data in purchase_data.items:
        product = await _get_product_by_sku(pharmacy_id, item_data.product_sku, db)
        ptr = item_data.cost_price_per_unit
        taxable = int(item_data.qty_units * ptr * 100)
        gst_amount = int(taxable * item_data.gst_percent / 100) if purchase_data.with_gst else 0
        line_total = taxable + gst_amount

        item_orm = PurchaseItemORM(
            product_id=product.id,
            product_name=item_data.product_name,
            batch_number=item_data.batch_no,
            expiry_date=date.fromisoformat(
                item_data.expiry_date[:10]) if item_data.expiry_date else None,
            hsn_code=product.hsn_code,
            quantity_ordered=item_data.qty_units,
            quantity_received=0,
            free_qty_units=item_data.free_qty_units or 0,
            units_per_pack=product.units_per_pack,
            mrp_paise=int(item_data.mrp_per_unit * 100),
            cost_price_paise=int(ptr * 100),
            discount_percent=0,
            gst_rate=item_data.gst_percent,
            cgst_rate=item_data.gst_percent / 2,
            sgst_rate=item_data.gst_percent / 2,
            taxable_amount_paise=taxable,
            gst_amount_paise=gst_amount,
            line_total_paise=line_total,
        )
        item_orms.append(item_orm)
        subtotal_paise += taxable
        tax_paise += gst_amount

    # Same class of bug fixed the same day in billing.py's create_bill: an
    # empty `items: []` used to sail straight through to a real, numbered
    # purchase order (draft or "confirmed and paid") with nothing on it —
    # live-confirmed (PUR-2026-3261, confirmed/paid, ₹0.00, zero items).
    # Reject before the purchase number is consumed by an actual row.
    if not item_orms:
        raise HTTPException(
            status_code=400,
            detail="Add at least one medicine to create a purchase.")

    # Same net-amount formula InvoiceBreakdownModal.jsx already computes and
    # shows the pharmacist before they click Confirm & Save — these used to
    # be silently discarded (see migration c5671e4dfe9f).
    discount_paise = int(round(purchase_data.total_discount * 100))
    cess_paise = int(round(purchase_data.cess * 100))
    adjusted_cn_paise = int(round(purchase_data.adjusted_cn * 100))
    tcs_paise = int(round(purchase_data.tcs * 100))
    extra_charges_paise = int(round(purchase_data.extra_charges * 100))
    adjustment_amount_paise = int(round(purchase_data.adjustment_amount * 100))

    net_before_round_paise = (
        subtotal_paise + tax_paise - discount_paise + cess_paise
        - adjusted_cn_paise + tcs_paise + extra_charges_paise + adjustment_amount_paise
    )
    # Round to nearest rupee
    grand_total_paise = round(net_before_round_paise / 100) * 100

    status = purchase_data.status or "draft"
    payment_status = purchase_data.payment_status or "unpaid"
    if purchase_data.purchase_on == "cash" and status == "confirmed":
        payment_status = "paid"

    due_dt: date | None = None
    if purchase_data.due_date:
        due_dt = date.fromisoformat(purchase_data.due_date[:10])
    elif purchase_data.purchase_on == "credit":
        purchase_dt = date.fromisoformat(purchase_data.purchase_date[:10])
        due_dt = purchase_dt + timedelta(days=supplier.credit_days or 30)

    purchase = PurchaseORM(
        pharmacy_id=pharmacy_id,
        supplier_id=supplier_id,
        purchase_number=purchase_number,
        supplier_invoice_number=purchase_data.supplier_invoice_no,
        supplier_invoice_date=date.fromisoformat(
            purchase_data.supplier_invoice_date[:10]) if purchase_data.supplier_invoice_date else None,
        purchase_date=date.fromisoformat(purchase_data.purchase_date[:10]),
        due_date=due_dt,
        order_type=purchase_data.order_type,
        with_gst=purchase_data.with_gst,
        purchase_on=purchase_data.purchase_on,
        subtotal_paise=subtotal_paise,
        total_discount_paise=discount_paise,
        cess_paise=cess_paise,
        adjusted_cn_paise=adjusted_cn_paise,
        tcs_paise=tcs_paise,
        extra_charges_paise=extra_charges_paise,
        adjustment_amount_paise=adjustment_amount_paise,
        total_gst_paise=tax_paise,
        total_cgst_paise=tax_paise // 2,
        total_sgst_paise=tax_paise - tax_paise // 2,
        grand_total_paise=grand_total_paise,
        amount_paid_paise=grand_total_paise if payment_status == "paid" else 0,
        status=status,
        payment_status=payment_status,
        notes=purchase_data.note,
        invoice_attachment_data=purchase_data.invoice_attachment_data,
        invoice_attachment_name=purchase_data.invoice_attachment_name,
        created_by=uuid.UUID(current_user.id),
    )
    db.add(purchase)
    await db.flush()

    # Link items to purchase
    for item_orm in item_orms:
        item_orm.purchase_id = purchase.id
        db.add(item_orm)
    await db.flush()

    # Create stock if confirmed
    if status == "confirmed":
        received_overrides = {
            i: d.received_qty_units for i, d in enumerate(purchase_data.items)
            if d.received_qty_units is not None
        }
        await _create_stock_for_items(
            purchase, item_orms, pharmacy_id, uuid.UUID(current_user.id), db, received_overrides)

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "purchase", purchase.id,
        {"purchase_number": purchase_number,
         "status": status,
         "total_value": grand_total_paise / 100,
         "payment_status": payment_status},
        db, ip_address=_client_ip(request),
    )
    await db.flush()

    return await _purchase_response(purchase, item_orms, db)


@router.put("/purchases/{purchase_id}")
async def update_purchase(
        purchase_id: str,
        purchase_data: PurchaseCreate,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    await _require_purchases_permission(current_user, "edit", db)
    if purchase_data.invoice_attachment_data:
        _validate_invoice_attachment(purchase_data.invoice_attachment_data)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    pid = uuid.UUID(purchase_id)

    purchase = await get_owned_or_404(
        db, PurchaseORM, pid, pharmacy_id, not_found_detail="Purchase not found",
        extra_conditions=[PurchaseORM.deleted_at.is_(None)])
    old_status = purchase.status
    old_total_value = purchase.grand_total_paise / 100
    if purchase.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft purchases can be edited")

    # Just verifying ownership here — unlike create_purchase, this path
    # never needs the supplier row itself (no due_date recompute on edit).
    await get_owned_or_404(
        db, SupplierORM, purchase_data.supplier_id, pharmacy_id, not_found_detail="Supplier not found")

    # Delete old items
    old_items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
    for old_item in old_items_result.scalars().all():
        await db.delete(old_item)
    await db.flush()

    # Rebuild items
    subtotal_paise = 0
    tax_paise = 0
    item_orms: list[PurchaseItemORM] = []

    for item_data in purchase_data.items:
        product = await _get_product_by_sku(pharmacy_id, item_data.product_sku, db)
        ptr = item_data.cost_price_per_unit
        taxable = int(item_data.qty_units * ptr * 100)
        gst_amount = int(taxable * item_data.gst_percent / 100) if purchase_data.with_gst else 0
        line_total = taxable + gst_amount

        item_orm = PurchaseItemORM(
            purchase_id=pid,
            product_id=product.id,
            product_name=item_data.product_name,
            batch_number=item_data.batch_no,
            expiry_date=date.fromisoformat(
                item_data.expiry_date[:10]) if item_data.expiry_date else None,
            hsn_code=product.hsn_code,
            quantity_ordered=item_data.qty_units,
            quantity_received=0,
            free_qty_units=item_data.free_qty_units or 0,
            units_per_pack=product.units_per_pack,
            mrp_paise=int(item_data.mrp_per_unit * 100),
            cost_price_paise=int(ptr * 100),
            discount_percent=0,
            gst_rate=item_data.gst_percent,
            cgst_rate=item_data.gst_percent / 2,
            sgst_rate=item_data.gst_percent / 2,
            taxable_amount_paise=taxable,
            gst_amount_paise=gst_amount,
            line_total_paise=line_total,
        )
        item_orms.append(item_orm)
        db.add(item_orm)
        subtotal_paise += taxable
        tax_paise += gst_amount

    # Same check as create_purchase — without it, emptying a draft's items
    # and saving (even as "confirmed") silently produces a real purchase
    # order with nothing on it. The old items above are only flushed, not
    # committed, so rejecting here still lets get_db's rollback restore them.
    if not item_orms:
        raise HTTPException(
            status_code=400,
            detail="Add at least one medicine to save this purchase.")

    discount_paise = int(round(purchase_data.total_discount * 100))
    cess_paise = int(round(purchase_data.cess * 100))
    adjusted_cn_paise = int(round(purchase_data.adjusted_cn * 100))
    tcs_paise = int(round(purchase_data.tcs * 100))
    extra_charges_paise = int(round(purchase_data.extra_charges * 100))
    adjustment_amount_paise = int(round(purchase_data.adjustment_amount * 100))

    net_before_round_paise = (
        subtotal_paise + tax_paise - discount_paise + cess_paise
        - adjusted_cn_paise + tcs_paise + extra_charges_paise + adjustment_amount_paise
    )
    grand_total_paise = round(net_before_round_paise / 100) * 100
    status = purchase_data.status or "draft"

    purchase.supplier_id = uuid.UUID(purchase_data.supplier_id)
    purchase.purchase_date = date.fromisoformat(purchase_data.purchase_date[:10])
    purchase.supplier_invoice_number = purchase_data.supplier_invoice_no
    purchase.supplier_invoice_date = date.fromisoformat(
        purchase_data.supplier_invoice_date[:10]) if purchase_data.supplier_invoice_date else None
    purchase.order_type = purchase_data.order_type
    purchase.with_gst = purchase_data.with_gst
    purchase.purchase_on = purchase_data.purchase_on
    purchase.subtotal_paise = subtotal_paise
    purchase.total_discount_paise = discount_paise
    purchase.cess_paise = cess_paise
    purchase.adjusted_cn_paise = adjusted_cn_paise
    purchase.tcs_paise = tcs_paise
    purchase.extra_charges_paise = extra_charges_paise
    purchase.adjustment_amount_paise = adjustment_amount_paise
    purchase.total_gst_paise = tax_paise
    purchase.total_cgst_paise = tax_paise // 2
    purchase.total_sgst_paise = tax_paise - tax_paise // 2
    purchase.grand_total_paise = grand_total_paise
    purchase.status = status
    purchase.notes = purchase_data.note
    purchase.invoice_attachment_data = purchase_data.invoice_attachment_data
    purchase.invoice_attachment_name = purchase_data.invoice_attachment_name

    await db.flush()

    # Create stock if transitioning draft → confirmed
    if status == "confirmed":
        received_overrides = {
            i: d.received_qty_units for i, d in enumerate(purchase_data.items)
            if d.received_qty_units is not None
        }
        await _create_stock_for_items(
            purchase, item_orms, pharmacy_id, uuid.UUID(current_user.id), db, received_overrides)

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update", "purchase", purchase.id,
        {"status": status, "total_value": grand_total_paise / 100}, db,
        old_values={"status": old_status, "total_value": old_total_value},
        ip_address=_client_ip(request),
    )
    await db.flush()
    # purchase.updated_at has onupdate=func.now() — the flush above expires it
    # server-side, and touching it in _purchase_response() without an explicit
    # async refresh first throws MissingGreenlet (sync lazy-load attempted in
    # an async context). Refresh eagerly here instead of letting it lazy-load.
    await db.refresh(purchase)

    return await _purchase_response(purchase, item_orms, db)


@router.put("/purchases/{purchase_id}/correct")
async def correct_confirmed_purchase(
        purchase_id: str,
        correction: PurchaseCorrectionRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """The only way to fix a real mistake on an already-confirmed
    purchase — update_purchase() above refuses any edit once
    status != "draft" by design. That refusal was only ever half of
    "don't allow silent editing" (docs/23_PURCHASES_ACCEPTANCE_SPEC.md
    UC-P09: a confirmed purchase was permanent, forever, even when
    wrong). Admin-only, a reason is mandatory, every change is
    audit-logged old-vs-new. See PurchaseCorrectionRequest for why
    quantity is deliberately excluded.
    """
    if not correction.reason or not correction.reason.strip():
        raise HTTPException(
            status_code=400, detail="A reason is required to correct a confirmed purchase")
    await require_admin_or_super(
        current_user, db, detail="Only admins can correct a confirmed purchase")

    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    pid = uuid.UUID(purchase_id)
    purchase = await get_owned_or_404(
        db, PurchaseORM, pid, pharmacy_id, not_found_detail="Purchase not found",
        extra_conditions=[PurchaseORM.deleted_at.is_(None)])
    if purchase.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Only a confirmed purchase is corrected here — a draft is already directly editable")

    old_values: dict = {}
    new_values: dict = {"reason": correction.reason.strip()}

    if (correction.supplier_invoice_number is not None
            and correction.supplier_invoice_number != purchase.supplier_invoice_number):
        old_values["supplier_invoice_number"] = purchase.supplier_invoice_number
        new_values["supplier_invoice_number"] = correction.supplier_invoice_number
        purchase.supplier_invoice_number = correction.supplier_invoice_number

    if correction.supplier_invoice_date is not None:
        new_inv_date = date.fromisoformat(correction.supplier_invoice_date[:10])
        if new_inv_date != purchase.supplier_invoice_date:
            old_values["supplier_invoice_date"] = (
                purchase.supplier_invoice_date.isoformat() if purchase.supplier_invoice_date else None)
            new_values["supplier_invoice_date"] = new_inv_date.isoformat()
            purchase.supplier_invoice_date = new_inv_date

    if correction.notes is not None and correction.notes != purchase.notes:
        old_values["notes"] = purchase.notes
        new_values["notes"] = correction.notes
        purchase.notes = correction.notes

    item_changes: list[dict] = []
    if correction.items:
        items_result = await db.execute(
            select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
        items_by_id = {str(i.id): i for i in items_result.scalars().all()}

        for ic in correction.items:
            item = items_by_id.get(ic.item_id)
            if not item:
                raise HTTPException(
                    status_code=404,
                    detail=f"Purchase item {ic.item_id} not found on this purchase")

            batch = None
            if item.batch_id:
                batch = await get_owned_or_404(
                    db, BatchORM, item.batch_id, pharmacy_id,
                    not_found_detail="Linked stock batch not found")

            item_change = {"item_id": ic.item_id, "product_name": item.product_name}

            if ic.mrp_per_unit is not None:
                new_mrp_paise = int(round(ic.mrp_per_unit * 100))
                if new_mrp_paise <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"MRP for {item.product_name} must be greater than ₹0")
                if new_mrp_paise != item.mrp_paise:
                    item_change["mrp"] = {"old": item.mrp_paise / 100, "new": new_mrp_paise / 100}
                    item.mrp_paise = new_mrp_paise
                    if batch:
                        batch.mrp_paise = new_mrp_paise

            if ic.cost_price_per_unit is not None:
                new_cost_paise = int(round(ic.cost_price_per_unit * 100))
                if new_cost_paise <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cost price for {item.product_name} must be greater than ₹0")
                if new_cost_paise != item.cost_price_paise:
                    item_change["cost_price"] = {
                        "old": item.cost_price_paise / 100, "new": new_cost_paise / 100}
                    item.cost_price_paise = new_cost_paise
                    # Cost price drives taxable_amount_paise for this item
                    # (same formula create_purchase/update_purchase use) —
                    # recomputed for the whole purchase below so a
                    # corrected PTR doesn't leave the grand total wrong.
                    item.taxable_amount_paise = int(item.quantity_ordered * new_cost_paise)
                    item.gst_amount_paise = (
                        int(item.taxable_amount_paise * float(item.gst_rate) / 100)
                        if purchase.with_gst else 0)
                    item.line_total_paise = item.taxable_amount_paise + item.gst_amount_paise
                    if batch:
                        batch.cost_price_paise = new_cost_paise

            if ic.batch_no is not None and ic.batch_no.strip() and ic.batch_no.strip() != item.batch_number:
                new_batch_no = ic.batch_no.strip()
                dup = await db.execute(select(BatchORM).where(
                    BatchORM.product_id == item.product_id,
                    BatchORM.batch_number == new_batch_no,
                    BatchORM.is_active.is_(True),
                    BatchORM.id != (batch.id if batch else uuid.uuid4()),
                ))
                if dup.scalar_one_or_none():
                    raise HTTPException(
                        status_code=400,
                        detail=f"A batch numbered '{new_batch_no}' already exists for {item.product_name}")
                item_change["batch_number"] = {"old": item.batch_number, "new": new_batch_no}
                item.batch_number = new_batch_no
                if batch:
                    batch.batch_number = new_batch_no

            if ic.expiry_date is not None:
                new_expiry = date.fromisoformat(ic.expiry_date[:10])
                if new_expiry != item.expiry_date:
                    item_change["expiry_date"] = {
                        "old": item.expiry_date.isoformat() if item.expiry_date else None,
                        "new": new_expiry.isoformat()}
                    item.expiry_date = new_expiry
                    if batch:
                        batch.expiry_date = new_expiry

            if len(item_change) > 2:
                item_changes.append(item_change)

        if item_changes:
            all_items_result = await db.execute(
                select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
            all_items = all_items_result.scalars().all()
            old_grand_total = purchase.grand_total_paise / 100
            subtotal_paise = sum(it.taxable_amount_paise for it in all_items)
            tax_paise = sum(it.gst_amount_paise for it in all_items)
            net_before_round_paise = (
                subtotal_paise + tax_paise - purchase.total_discount_paise + purchase.cess_paise
                - purchase.adjusted_cn_paise + purchase.tcs_paise + purchase.extra_charges_paise
                + purchase.adjustment_amount_paise
            )
            purchase.subtotal_paise = subtotal_paise
            purchase.total_gst_paise = tax_paise
            purchase.total_cgst_paise = tax_paise // 2
            purchase.total_sgst_paise = tax_paise - tax_paise // 2
            purchase.grand_total_paise = round(net_before_round_paise / 100) * 100
            if purchase.grand_total_paise != int(old_grand_total * 100):
                old_values["grand_total"] = old_grand_total
                new_values["grand_total"] = purchase.grand_total_paise / 100

    if item_changes:
        new_values["items"] = item_changes

    if len(new_values) == 1:  # only "reason" — nothing actually changed
        raise HTTPException(status_code=400, detail="No changes were provided to correct")

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "correct", "purchase", purchase.id,
        new_values, db, old_values=old_values, ip_address=_client_ip(request),
    )
    await db.flush()
    await db.refresh(purchase)

    items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
    return await _purchase_response(purchase, items_result.scalars().all(), db)


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(
        purchase_id: str,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """Soft-delete only, and only ever a draft — a draft has never touched
    stock or supplier balances (see _create_stock_for_items, only called on
    confirm), so there's nothing to reverse. A confirmed purchase has real
    downstream effects and needs a real reversal mechanism, not a delete
    (tracked separately, not this endpoint)."""
    await _require_purchases_permission(current_user, "edit", db)
    pid = uuid.UUID(purchase_id)

    purchase = await get_owned_or_404(
        db, PurchaseORM, pid, uuid.UUID(current_user.pharmacy_id), not_found_detail="Purchase not found",
        extra_conditions=[PurchaseORM.deleted_at.is_(None)])
    if purchase.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft purchases can be deleted")

    purchase.deleted_at = datetime.now(timezone.utc)
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "delete", "purchase", purchase.id,
        {"purchase_number": purchase.purchase_number}, db,
        old_values={"deleted_at": None}, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Draft purchase deleted"}


# Static route — must be registered before the parameterized
# /purchases/{purchase_id} below, same convention as inventory.py's
# /products/* routes.
@router.get("/purchases/check-duplicate-invoice")
async def check_duplicate_invoice(
        supplier_id: str, invoice_no: str, exclude_id: Optional[str] = None,
        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Warns, does not block — a real distributor invoice can legitimately
    need re-entry (e.g. correcting an earlier mistake), so this is advisory
    only. Case-insensitive exact match, scoped to the same supplier (the
    same invoice number from two different suppliers is not a duplicate).
    Excludes soft-deleted purchases and, when editing, the purchase being
    edited itself."""
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    invoice_no = invoice_no.strip()
    if not invoice_no:
        return {"duplicate": False}

    query = select(PurchaseORM).where(
        PurchaseORM.pharmacy_id == pharmacy_id,
        PurchaseORM.supplier_id == uuid.UUID(supplier_id),
        PurchaseORM.deleted_at.is_(None),
        func.lower(PurchaseORM.supplier_invoice_number) == invoice_no.lower(),
    )
    if exclude_id:
        query = query.where(PurchaseORM.id != uuid.UUID(exclude_id))

    result = await db.execute(query.order_by(PurchaseORM.created_at.desc()).limit(1))
    existing = result.scalar_one_or_none()
    if not existing:
        return {"duplicate": False}

    return {
        "duplicate": True,
        "purchase_id": str(existing.id),
        "purchase_number": existing.purchase_number,
        "purchase_date": existing.purchase_date.isoformat() if existing.purchase_date else None,
    }


# Static route — must be registered before the parameterized
# /purchases/{purchase_id} below, same convention as check-duplicate-invoice.
@router.get("/purchases/last-purchase-price")
async def get_last_purchase_price(
        product_sku: str,
        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    """Advisory (never blocking), Sep 25, 2026 — the Purchase entry screen's
    price-change warning needs to know what this product last cost so a
    real jump ("₹8 -> ₹10") isn't silently missed. Any supplier, most
    recent CONFIRMED purchase (a draft never really happened, and a
    different supplier's rate is still the real market signal a
    pharmacist cares about — direct product decision, see
    docs/07_BUSINESS_LOGIC.md)."""
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    product = await _get_product_by_sku(pharmacy_id, product_sku, db)

    result = await db.execute(
        select(PurchaseItemORM, PurchaseORM.purchase_date)
        .join(PurchaseORM, PurchaseItemORM.purchase_id == PurchaseORM.id)
        .where(
            PurchaseORM.pharmacy_id == pharmacy_id,
            PurchaseORM.status == "confirmed",
            PurchaseORM.deleted_at.is_(None),
            PurchaseItemORM.product_id == product.id,
        )
        .order_by(PurchaseORM.purchase_date.desc(), PurchaseORM.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if not row:
        return {"found": False}
    item, purchase_date = row
    return {
        "found": True,
        "cost_price_per_unit": item.cost_price_paise / 100,
        "mrp_per_unit": item.mrp_paise / 100,
        "purchase_date": purchase_date.isoformat() if purchase_date else None,
    }


@router.get("/purchases/{purchase_id}")
async def get_purchase(purchase_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    purchase = await get_owned_or_404(
        db, PurchaseORM, purchase_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Purchase not found",
        extra_conditions=[PurchaseORM.deleted_at.is_(None)])

    items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == purchase.id))
    items = items_result.scalars().all()

    resp = await _purchase_response(purchase, items, db)

    # Enrich with supplier name
    # tenant-safe: purchase already scoped via get_owned_or_404
    sup_result = await db.execute(select(SupplierORM.name).where(SupplierORM.id == purchase.supplier_id))
    sup_name = sup_result.scalar_one_or_none()
    resp["supplier_name"] = sup_name or ""
    resp["last_payment_date"] = await _get_last_payment_date(purchase.id, db)

    return resp


@router.post("/purchases/{purchase_id}/pay")
async def mark_purchase_paid(
        purchase_id: str,
        payment: PurchasePaymentRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    await _require_purchases_permission(current_user, "edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    pid = uuid.UUID(purchase_id)

    purchase = await get_owned_or_404(
        db, PurchaseORM, pid, pharmacy_id, not_found_detail="Purchase not found")
    if purchase.payment_status == "paid":
        raise HTTPException(status_code=400, detail="Purchase is already fully paid")

    old_payment_status = purchase.payment_status
    old_amount_paid = purchase.amount_paid_paise / 100
    payment_paise = int(payment.amount * 100)
    outstanding_paise = purchase.grand_total_paise - purchase.amount_paid_paise

    if payment_paise <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    if payment_paise > outstanding_paise:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount exceeds the outstanding balance of ₹{outstanding_paise / 100:.2f}",
        )

    new_paid = purchase.amount_paid_paise + payment_paise
    payment_status = "paid" if new_paid >= purchase.grand_total_paise else "partial"

    purchase.amount_paid_paise = new_paid
    purchase.payment_status = payment_status

    # PurchasePayment.payment_date already existed on the model/table
    # (server_default=CURRENT_DATE) but this request never accepted or
    # forwarded the date the pharmacist actually picked in the modal —
    # every payment silently recorded today's date regardless.
    payment_dt = date.fromisoformat(payment.payment_date[:10]) if payment.payment_date else date.today()

    # Record payment
    db.add(PurchasePaymentORM(
        pharmacy_id=pharmacy_id,
        purchase_id=pid,
        amount_paise=payment_paise,
        payment_method=payment.payment_method,
        payment_date=payment_dt,
        reference_number=payment.reference_no,
        notes=payment.notes,
        created_by=uuid.UUID(current_user.id),
    ))

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "payment", "purchase", pid,
        {"amount": payment.amount,
         "payment_method": payment.payment_method,
         "payment_date": payment_dt.isoformat(),
         "payment_status": payment_status},
        db,
        old_values={"payment_status": old_payment_status, "amount_paid": old_amount_paid},
        ip_address=_client_ip(request),
    )
    await db.flush()
    await db.refresh(purchase)  # see comment on the same pattern in update_purchase()

    items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
    resp = await _purchase_response(purchase, items_result.scalars().all(), db)
    # Not simply payment_dt — a backdated payment_date on this payment
    # could still be older than an existing payment's date, so the true
    # most-recent-by-date must be looked up rather than assumed.
    resp["last_payment_date"] = await _get_last_payment_date(pid, db)
    return resp


@router.get("/purchases/{purchase_id}/payments")
async def list_purchase_payments(
        purchase_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """Individual PurchasePayment rows were recorded by /pay above since
    day one, but nothing ever exposed them — the purchase response only
    ever carried the aggregate amount_paid/last_payment_date, so there
    was no way to see (or reverse) one specific payment. Needed to make
    UC-P31's reversal endpoint below actually reachable from the UI."""
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    pid = uuid.UUID(purchase_id)
    await get_owned_or_404(
        db, PurchaseORM, pid, pharmacy_id, not_found_detail="Purchase not found")

    result = await db.execute(
        select(PurchasePaymentORM)
        .where(PurchasePaymentORM.purchase_id == pid)
        .order_by(PurchasePaymentORM.payment_date.desc(), PurchasePaymentORM.created_at.desc())
    )
    return [
        {
            "id": str(p.id),
            "amount": p.amount_paise / 100,
            "payment_method": p.payment_method,
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "reference_number": p.reference_number,
            "notes": p.notes,
            "reversed": p.reversed_at is not None,
            "reversed_at": p.reversed_at.isoformat() if p.reversed_at else None,
            "reversal_reason": p.reversal_reason,
        }
        for p in result.scalars().all()
    ]


@router.post("/purchases/{purchase_id}/payments/{payment_id}/reverse")
async def reverse_purchase_payment(
        purchase_id: str,
        payment_id: str,
        reversal: PaymentReversalRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """UC-P31 (docs/23_PURCHASES_ACCEPTANCE_SPEC.md) — a payment recorded
    with the wrong amount/method/date was permanent forever; there was no
    way to reverse it. Admin-only, mandatory reason. Soft-reverses (sets
    reversed_at/reversed_by/reversal_reason on the payment row, never
    deletes it — Manifesto rule 6) and re-derives the purchase's
    amount_paid_paise/payment_status from the sum of its remaining
    non-reversed payments, rather than just subtracting this one amount,
    so it can't drift if reversals ever happen out of order.
    """
    if not reversal.reason or not reversal.reason.strip():
        raise HTTPException(
            status_code=400, detail="A reason is required to reverse a payment")
    await require_admin_or_super(
        current_user, db, detail="Only admins can reverse a payment")

    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    pid = uuid.UUID(purchase_id)
    purchase = await get_owned_or_404(
        db, PurchaseORM, pid, pharmacy_id, not_found_detail="Purchase not found")

    payment = await get_owned_or_404(
        db, PurchasePaymentORM, uuid.UUID(payment_id), pharmacy_id,
        not_found_detail="Payment not found",
        extra_conditions=[PurchasePaymentORM.purchase_id == pid])
    if payment.reversed_at is not None:
        raise HTTPException(status_code=400, detail="This payment was already reversed")

    old_amount_paid = purchase.amount_paid_paise / 100
    old_payment_status = purchase.payment_status

    payment.reversed_at = datetime.now(timezone.utc)
    payment.reversed_by = uuid.UUID(current_user.id)
    payment.reversal_reason = reversal.reason.strip()
    await db.flush()

    remaining_result = await db.execute(
        select(func.sum(PurchasePaymentORM.amount_paise))
        .where(PurchasePaymentORM.purchase_id == pid, PurchasePaymentORM.reversed_at.is_(None))
    )
    remaining_paise = remaining_result.scalar_one_or_none() or 0
    purchase.amount_paid_paise = remaining_paise
    if remaining_paise <= 0:
        purchase.payment_status = "unpaid"
    elif remaining_paise >= purchase.grand_total_paise:
        purchase.payment_status = "paid"
    else:
        purchase.payment_status = "partial"

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "reverse_payment", "purchase", pid,
        {"reversed_payment_amount": payment.amount_paise / 100,
         "reason": reversal.reason.strip(),
         "amount_paid": purchase.amount_paid_paise / 100,
         "payment_status": purchase.payment_status},
        db,
        old_values={"amount_paid": old_amount_paid, "payment_status": old_payment_status},
        ip_address=_client_ip(request),
    )
    await db.flush()
    await db.refresh(purchase)

    items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
    resp = await _purchase_response(purchase, items_result.scalars().all(), db)
    resp["last_payment_date"] = await _get_last_payment_date(pid, db)
    return resp
