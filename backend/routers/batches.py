from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from constants import PRODUCT_CATEGORIES
from deps import DbSession
from models.billing import Bill as BillORM, SalesReturn as SalesReturnORM
from models.products import Product as ProductORM, StockBatch as BatchORM, StockMovement as MovementORM
from models.purchases import (
    Purchase as PurchaseORM, PurchaseItem as PurchaseItemORM, PurchaseReturn as PurchaseReturnORM,
)
from models.users import AuditLog
from routers.auth_helpers import (
    User, get_current_user, get_owned_or_404, has_permission, require_admin_or_super,
)

# Real, navigable references only — "adjustment"/"writeoff" store a
# randomly generated reference_id (see _record_movement callers below)
# that points to no real record, so they're deliberately excluded here
# rather than resolved into a broken link. Maps reference_type -> (ORM
# class, its human-readable number column, the frontend route to link to).
_REFERENCE_LOOKUPS = {
    "invoice":          (BillORM, "bill_number", "/billing/{id}"),
    "purchase":         (PurchaseORM, "purchase_number", "/purchases/{id}"),
    "sales_return":     (SalesReturnORM, "return_number", "/billing/returns/{id}"),
    "purchase_return":  (PurchaseReturnORM, "return_number", "/purchases/returns/{id}"),
}

router = APIRouter(prefix="/api", tags=["batches"])

# Same single source of truth the Add Medicine form's Category dropdown uses
# (constants.py) — never a second, hand-typed label list to drift from it.
_CATEGORY_LABELS = {c["value"]: c["label"] for c in PRODUCT_CATEGORIES}


# ── Pydantic request models ──────────────────────────────────────────────────

def _validate_batch_no(v: str) -> str:
    # Rule 65, Drugs and Cosmetics Rules 1945: the batch number on a sale
    # invoice must trace back to a real manufacturer batch — required for
    # every schedule, not just H/H1, since every unit of stock in this
    # system (any product, any schedule) lives inside a batch record, and
    # expiry tracking/FEFO/recall lookups all depend on it being real. A
    # frontend fallback used to silently invent one ("INIT-<timestamp>")
    # when left blank; fixed to require a real value here so no client can
    # bypass that by calling this endpoint directly.
    if not v or not v.strip():
        raise ValueError("Batch number is required — every unit of stock must trace back to a real batch")
    return v.strip()


class StockBatchCreate(BaseModel):
    product_sku: str
    batch_no: str
    manufacture_date: Optional[str] = None
    expiry_date: str
    qty_on_hand: int
    cost_price_per_unit: float
    mrp_per_unit: float
    supplier_name: Optional[str] = None
    supplier_invoice_no: Optional[str] = None
    received_date: Optional[str] = None
    free_qty_units: Optional[int] = 0
    notes: Optional[str] = None

    _v_batch_no = field_validator("batch_no")(_validate_batch_no)


class StockBatchUpdate(BaseModel):
    batch_no: Optional[str] = None
    manufacture_date: Optional[str] = None
    expiry_date: Optional[str] = None
    qty_on_hand: Optional[int] = None
    cost_price_per_unit: Optional[float] = None
    mrp_per_unit: Optional[float] = None
    supplier_name: Optional[str] = None
    supplier_invoice_no: Optional[str] = None
    received_date: Optional[str] = None
    free_qty_units: Optional[int] = None
    notes: Optional[str] = None

    # Same rule as create — a batch's number can be corrected, never cleared.
    _v_batch_no = field_validator("batch_no")(_validate_batch_no)


class StockMovementCreate(BaseModel):
    product_sku: str
    batch_id: str
    product_name: str
    batch_no: str
    qty_delta_units: int
    movement_type: str
    ref_type: str
    ref_id: str
    reason: Optional[str] = None


class StockAdjustment(BaseModel):
    batch_id: str
    adjustment_type: str
    qty_units: int
    reason: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _batch_response(b: BatchORM, product: ProductORM) -> dict:
    return {
        "id": str(b.id),
        "product_sku": product.sku,
        "product_name": product.name,
        "product_brand": product.brand or "",
        "batch_no": b.batch_number,
        "manufacture_date": b.manufacture_date.isoformat() if b.manufacture_date else None,
        "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
        # qty_on_hand and total_units are both already real units (migration
        # a343c922f896) — kept as two keys for API back-compat, same value.
        "qty_on_hand": b.quantity_on_hand,
        "total_units": b.quantity_on_hand,
        "cost_price_per_unit": b.cost_price_paise / 100,
        "mrp_per_unit": b.mrp_paise / 100,
        # gst_percent/category/discount_percent are the product's own
        # values (not per-batch) — added Sep 15, 2026 so the Billing page's
        # batch panel can show them without a second fetch. discount_percent
        # is real here; the frontend's old "Prev MRP" column read a field
        # (prev_mrp) that never existed on this response at all — same
        # fabricated-field class as the Aug 23, 2026 Medicine Detail fix —
        # dropped rather than backfilled with another guess.
        "gst_percent": float(product.gst_rate),
        "category": product.category,
        "category_label": _CATEGORY_LABELS.get(product.category, product.category or "—"),
        "discount_percent": float(product.discount_percent),
        "is_active": b.is_active,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _movement_response(
    m: MovementORM, product: Optional[ProductORM], batch: Optional[BatchORM],
    ref_number: Optional[str],
) -> dict:
    ref_path = None
    if ref_number and m.reference_type in _REFERENCE_LOOKUPS:
        ref_path = _REFERENCE_LOOKUPS[m.reference_type][2].format(id=str(m.reference_id))
    return {
        "id": str(m.id),
        "product_id": str(m.product_id),
        "product_name": product.name if product else None,
        "product_sku": product.sku if product else None,
        "batch_id": str(m.batch_id),
        "batch_no": batch.batch_number if batch else None,
        "movement_type": m.movement_type,
        "qty_delta_units": m.quantity,
        "quantity_before": m.quantity_before,
        "quantity_after": m.quantity_after,
        "ref_type": m.reference_type,
        "ref_number": ref_number,
        "ref_path": ref_path,
        "reason": m.notes,
        "performed_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _get_product_by_sku(pharmacy_id: uuid.UUID, sku: str, db: AsyncSession) -> ProductORM:
    result = await db.execute(
        select(ProductORM).where(ProductORM.pharmacy_id == pharmacy_id, ProductORM.sku == sku)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def _get_batch(batch_id: str, pharmacy_id: uuid.UUID, db: AsyncSession) -> BatchORM:
    return await get_owned_or_404(
        db, BatchORM, batch_id, pharmacy_id, not_found_detail="Batch not found")


async def _require_inventory_permission(current_user: User, action: str, db: AsyncSession) -> None:
    """`inventory:batches_create`/`inventory:stock_adjust` are real,
    seeded permissions (constants.py, ROLE_PERMISSIONS) that nothing in
    this router ever called — found Sep 13, 2026 (Purchases follow-up):
    any authenticated user, including a plain cashier, could freely add a
    stock batch, adjust a batch's quantity, write off expired stock, or
    log a stock movement with no gate at all. Same pattern as
    `_require_purchases_permission` in purchases.py."""
    if not await has_permission(current_user, f"inventory:{action}", db):
        raise HTTPException(
            status_code=403,
            detail=f"Your role does not have permission to {action.replace('_', ' ')}")


async def _record_movement(
    pharmacy_id: uuid.UUID, product_id: uuid.UUID, batch_id: uuid.UUID,
    movement_type: str, quantity: int, qty_before: int, qty_after: int,
    ref_type: str, ref_id: uuid.UUID, user_id: uuid.UUID, notes: str | None,
    db: AsyncSession,
) -> MovementORM:
    movement = MovementORM(
        pharmacy_id=pharmacy_id, product_id=product_id, batch_id=batch_id,
        movement_type=movement_type, quantity=quantity,
        quantity_before=qty_before, quantity_after=qty_after,
        reference_type=ref_type, reference_id=ref_id,
        user_id=user_id, notes=notes,
    )
    db.add(movement)
    return movement


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    """Same shared shape as suppliers.py/inventory.py's own per-router copy.
    _record_movement above is the sanctioned audit trail for a quantity
    change; this covers everything else (MRP/cost/expiry edits, delete) —
    previously left no record at all (docs/15_ROADMAP.md KNOWN ISSUES,
    found by scripts/check_audit_log_coverage.py)."""
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── /stock/batches ─────────────────────────────────────────────────────────────

@router.post("/stock/batches")
async def create_stock_batch(batch_data: StockBatchCreate, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_inventory_permission(current_user, "batches_create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    product = await _get_product_by_sku(pharmacy_id, batch_data.product_sku, db)

    # Check duplicate batch — scoped to active batches so a number can be
    # reused once the original is written off/deactivated; see the
    # IntegrityError catch below for why this alone isn't race-safe.
    existing = await db.execute(
        select(BatchORM).where(
            BatchORM.product_id == product.id,
            BatchORM.batch_number == batch_data.batch_no,
            BatchORM.is_active.is_(True),
        )
    )
    duplicate_batch_detail = "Batch with this number already exists for this product at this location"
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=duplicate_batch_detail)

    expiry = date.fromisoformat(batch_data.expiry_date[:10])
    if expiry < date.today():
        raise HTTPException(status_code=400, detail="Expiry date has already passed")
    mfg = date.fromisoformat(
        batch_data.manufacture_date[:10]) if batch_data.manufacture_date else None

    batch = BatchORM(
        pharmacy_id=pharmacy_id,
        product_id=product.id,
        batch_number=batch_data.batch_no,
        expiry_date=expiry,
        manufacture_date=mfg,
        mrp_paise=int(batch_data.mrp_per_unit * 100),
        cost_price_paise=int(batch_data.cost_price_per_unit * 100),
        quantity_received=batch_data.qty_on_hand,
        quantity_on_hand=batch_data.qty_on_hand,
    )
    db.add(batch)
    try:
        await db.flush()
    except IntegrityError:
        # Same double-click/two-tabs race as purchases.py's
        # _create_stock_for_items — the SELECT above isn't atomic with
        # this INSERT. uq_batches_product_batchnumber_active (migration
        # 29481ee67a4b) is the real, race-safe gate.
        raise HTTPException(status_code=400, detail=duplicate_batch_detail)

    # quantity_received/quantity_on_hand above are stored directly, in real
    # units (migration a343c922f896) — the movement record must match, not
    # multiply by units_per_pack again. Before this fix the ledger's own
    # "quantity" figure disagreed with the batch's own stored field for
    # every opening-stock entry.
    await _record_movement(
        pharmacy_id=pharmacy_id, product_id=product.id, batch_id=batch.id,
        movement_type="opening_stock", quantity=batch_data.qty_on_hand,
        qty_before=0, qty_after=batch_data.qty_on_hand,
        ref_type="opening", ref_id=batch.id,
        user_id=uuid.UUID(current_user.id), notes="Initial stock entry", db=db,
    )
    await db.flush()

    return _batch_response(batch, product)


@router.get("/stock/batches")
async def get_stock_batches(
        product_sku: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    query = select(BatchORM).where(BatchORM.pharmacy_id == pharmacy_id)

    if product_sku:
        prod_result = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == pharmacy_id,
                ProductORM.sku == product_sku)
        )
        product = prod_result.scalar_one_or_none()
        if not product:
            return []
        query = query.where(BatchORM.product_id == product.id)

    result = await db.execute(query.order_by(BatchORM.expiry_date))
    batches = result.scalars().all()

    # Gather product info for all batches
    product_ids = {b.product_id for b in batches}
    prod_result = await db.execute(select(ProductORM).where(ProductORM.id.in_(product_ids)))
    products_by_id = {p.id: p for p in prod_result.scalars().all()}

    return [_batch_response(b, products_by_id[b.product_id])
            for b in batches if b.product_id in products_by_id]


@router.get("/stock/batches/{batch_id}")
async def get_stock_batch(batch_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    batch = await _get_batch(batch_id, uuid.UUID(current_user.pharmacy_id), db)
    # tenant-safe: batch already scoped via _get_batch
    prod_result = await db.execute(select(ProductORM).where(ProductORM.id == batch.product_id))
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _batch_response(batch, product)


@router.get("/stock/batches/{batch_id}/origin-purchase")
async def get_batch_origin_purchase(batch_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """A near-expiry/expired batch on Medicine Detail had no path to
    returning it to the supplier — a return is always initiated from a
    specific past Purchase (GET /purchases/{id}/items-for-return), and
    nothing pointed a batch back to the purchase it came from. Not every
    batch has one (a manually-added batch via POST /stock/batches never
    goes through a Purchase), so this is advisory, found:false when there
    isn't one, same shape as check-duplicate-invoice/last-purchase-price."""
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    await _get_batch(batch_id, pharmacy_id, db)  # tenant-scope check only

    result = await db.execute(
        select(PurchaseORM.id, PurchaseORM.purchase_number, PurchaseORM.status)
        .join(PurchaseItemORM, PurchaseItemORM.purchase_id == PurchaseORM.id)
        .where(PurchaseItemORM.batch_id == uuid.UUID(batch_id),
               PurchaseORM.pharmacy_id == pharmacy_id, PurchaseORM.deleted_at.is_(None))
        .order_by(PurchaseORM.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if not row or row.status != "confirmed":
        return {"found": False}
    return {"found": True, "purchase_id": str(row.id), "purchase_number": row.purchase_number}


@router.put("/stock/batches/{batch_id}")
async def update_stock_batch(
        batch_id: str,
        batch_data: StockBatchUpdate,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    await require_admin_or_super(current_user, db, detail="Only admins can update stock batches")

    batch = await _get_batch(batch_id, pharmacy_id, db)
    updates = batch_data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    field_map = {
        "batch_no": "batch_number",
        "qty_on_hand": "quantity_on_hand",
        "cost_price_per_unit": None,  # special handling
        "mrp_per_unit": None,  # special handling
    }

    # Every other quantity-mutating endpoint (billing, purchases,
    # purchase_returns, /adjust) records a StockMovement — this direct
    # PUT was the one silent exception. Capture the before-value so a
    # real quantity change gets the same audit trail.
    old_qty_on_hand = batch.quantity_on_hand

    # Non-quantity fields (MRP/cost/expiry/batch number/etc.) previously
    # left no record at all — qty_on_hand is deliberately excluded here
    # since _record_movement below is its own, more detailed audit trail
    # (before/after quantities, not just a raw value).
    old_values: dict = {}
    new_values: dict = {}

    for key, value in updates.items():
        if key == "qty_on_hand":
            setattr(batch, "quantity_on_hand", value)
            continue
        if key == "cost_price_per_unit":
            old_val = batch.cost_price_paise / 100
            if old_val != value:
                old_values[key] = old_val
                new_values[key] = value
            batch.cost_price_paise = int(value * 100)
        elif key == "mrp_per_unit":
            old_val = batch.mrp_paise / 100
            if old_val != value:
                old_values[key] = old_val
                new_values[key] = value
            batch.mrp_paise = int(value * 100)
        elif key == "expiry_date":
            new_expiry = date.fromisoformat(value[:10])
            if new_expiry < date.today():
                raise HTTPException(status_code=400, detail="Expiry date has already passed")
            if batch.expiry_date != new_expiry:
                old_values[key] = batch.expiry_date.isoformat() if batch.expiry_date else None
                new_values[key] = new_expiry.isoformat()
            batch.expiry_date = new_expiry
        elif key == "manufacture_date":
            new_mfg = date.fromisoformat(value[:10])
            if batch.manufacture_date != new_mfg:
                old_values[key] = batch.manufacture_date.isoformat() if batch.manufacture_date else None
                new_values[key] = new_mfg.isoformat()
            batch.manufacture_date = new_mfg
        else:
            col = field_map.get(key, key)
            if col and hasattr(batch, col):
                old_val = getattr(batch, col)
                if old_val != value:
                    old_values[key] = old_val
                    new_values[key] = value
                setattr(batch, col, value)

    if batch.quantity_on_hand != old_qty_on_hand:
        db.add(MovementORM(
            pharmacy_id=pharmacy_id, product_id=batch.product_id, batch_id=batch.id,
            movement_type="batch_edit", quantity=batch.quantity_on_hand - old_qty_on_hand,
            quantity_before=old_qty_on_hand, quantity_after=batch.quantity_on_hand,
            reference_type="batch_edit", reference_id=batch.id,
            user_id=uuid.UUID(current_user.id), notes="Direct batch quantity edit via PUT /stock/batches",
        ))

    if new_values:
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "update", "stock_batch", batch.id,
            new_values, db, old_values=old_values, ip_address=_client_ip(request),
        )

    await db.flush()
    return {"message": "Batch updated successfully"}


@router.delete("/stock/batches/{batch_id}")
async def delete_stock_batch(batch_id: str, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    await require_admin_or_super(current_user, db, detail="Only admins can delete stock batches")

    batch = await _get_batch(batch_id, pharmacy_id, db)
    if batch.quantity_on_hand > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete batch with stock. Adjust quantity to 0 first.")

    batch.is_active = False
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "delete", "stock_batch", batch.id,
        {"deleted": True}, db,
        old_values={"batch_number": batch.batch_number, "quantity_on_hand": batch.quantity_on_hand},
        ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Batch deleted successfully"}


# ── /batches/:id/adjust & writeoff ────────────────────────────────────────────

@router.post("/batches/{batch_id}/adjust")
async def adjust_stock(batch_id: str, adjustment: StockAdjustment, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_inventory_permission(current_user, "stock_adjust", db)
    batch = await _get_batch(batch_id, uuid.UUID(current_user.pharmacy_id), db)
    # tenant-safe: batch already scoped via _get_batch
    prod_result = await db.execute(select(ProductORM).where(ProductORM.id == batch.product_id))
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # qty_units is already in real units, same as quantity_on_hand — see
    # models/products.py's StockBatch comment (migration a343c922f896).
    qty_delta_units = adjustment.qty_units if adjustment.adjustment_type == "add" else -adjustment.qty_units
    old_qty = batch.quantity_on_hand
    new_qty = old_qty + qty_delta_units

    if new_qty < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove {adjustment.qty_units} units. Only {old_qty} units available.")

    batch.quantity_on_hand = new_qty

    await _record_movement(
        pharmacy_id=batch.pharmacy_id, product_id=batch.product_id, batch_id=batch.id,
        movement_type="adjustment", quantity=qty_delta_units,
        qty_before=old_qty, qty_after=new_qty,
        ref_type="adjustment", ref_id=uuid.uuid4(),
        user_id=uuid.UUID(current_user.id), notes=adjustment.reason, db=db,
    )
    await db.flush()

    return {"message": "Stock adjusted successfully", "new_qty_units": new_qty,
            "adjustment_units": qty_delta_units}


@router.post("/batches/{batch_id}/writeoff-expiry")
async def writeoff_expired_batch(batch_id: str, writeoff_data: dict, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_inventory_permission(current_user, "stock_adjust", db)
    batch = await _get_batch(batch_id, uuid.UUID(current_user.pharmacy_id), db)
    # tenant-safe: batch already scoped via _get_batch
    prod_result = await db.execute(select(ProductORM).where(ProductORM.id == batch.product_id))
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if batch.expiry_date and batch.expiry_date >= date.today():
        raise HTTPException(status_code=400, detail="Batch is not expired yet")

    # quantity_on_hand is already in real units (migration a343c922f896).
    qty_units = batch.quantity_on_hand
    if qty_units <= 0:
        raise HTTPException(status_code=400, detail="No stock to write off")

    old_qty = batch.quantity_on_hand
    batch.quantity_on_hand = 0
    batch.quantity_written_off = (batch.quantity_written_off or 0) + old_qty
    batch.is_active = False

    await _record_movement(
        pharmacy_id=batch.pharmacy_id, product_id=batch.product_id, batch_id=batch.id,
        movement_type="expiry_writeoff", quantity=-qty_units,
        qty_before=old_qty, qty_after=0,
        ref_type="writeoff", ref_id=uuid.uuid4(),
        user_id=uuid.UUID(current_user.id),
        notes=writeoff_data.get("reason", "Expired stock write-off"), db=db,
    )
    await db.flush()

    return {"message": "Expired stock written off successfully",
            "qty_written_off_units": qty_units, "batch_id": batch_id}


# ── /stock-movements ───────────────────────────────────────────────────────────

@router.post("/stock-movements")
async def create_stock_movement(movement_data: StockMovementCreate, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_inventory_permission(current_user, "stock_adjust", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    product = await _get_product_by_sku(pharmacy_id, movement_data.product_sku, db)
    batch = await _get_batch(movement_data.batch_id, pharmacy_id, db)

    # StockBatch.quantity_on_hand is in real units everywhere it's written
    # (billing.py, purchase_returns.py, /adjust above) — qty_delta_units is
    # also units, so no conversion (migration a343c922f896). This endpoint
    # used to log a movement without ever applying it to the batch; now it
    # does both, with the same negative-stock guard /adjust uses.
    old_qty = batch.quantity_on_hand
    new_qty = old_qty + movement_data.qty_delta_units
    if new_qty < 0:
        raise HTTPException(
            status_code=400,
            detail=(f"Cannot record this movement: batch {batch.batch_number} would go negative "
                    f"({old_qty} on hand, delta of {movement_data.qty_delta_units})"))

    batch.quantity_on_hand = new_qty

    movement = await _record_movement(
        pharmacy_id=pharmacy_id, product_id=product.id, batch_id=batch.id,
        movement_type=movement_data.movement_type, quantity=movement_data.qty_delta_units,
        qty_before=old_qty, qty_after=new_qty,
        ref_type=movement_data.ref_type, ref_id=uuid.UUID(
            movement_data.ref_id) if movement_data.ref_id else uuid.uuid4(),
        user_id=uuid.UUID(current_user.id), notes=movement_data.reason, db=db,
    )
    await db.flush()
    return {"message": "Stock movement recorded", "id": str(movement.id)}


@router.get("/stock-movements")
async def get_stock_movements(
    product_sku: Optional[str] = None, batch_id: Optional[str] = None,
    movement_type: Optional[str] = None,
    page: int = 1, page_size: int = 50,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    query = select(MovementORM).where(MovementORM.pharmacy_id == pharmacy_id)

    if product_sku:
        prod_result = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == pharmacy_id,
                ProductORM.sku == product_sku)
        )
        product = prod_result.scalar_one_or_none()
        if not product:
            return {
                "data": [],
                "pagination": {
                    "page": 1,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 1,
                    "has_next": False,
                    "has_prev": False}}
        query = query.where(MovementORM.product_id == product.id)
    if batch_id:
        query = query.where(MovementORM.batch_id == uuid.UUID(batch_id))
    if movement_type:
        query = query.where(MovementORM.movement_type == movement_type)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(MovementORM.created_at.desc()).offset(offset).limit(page_size))
    movements = result.scalars().all()

    # Bulk-fetch product/batch names and real reference document numbers for
    # this page only — avoids an N+1 query per row while still resolving
    # real, human-readable labels instead of raw internal UUIDs.
    products_by_id: dict = {}
    if movements:
        product_ids = {m.product_id for m in movements}
        prods = (await db.execute(select(ProductORM).where(ProductORM.id.in_(product_ids)))).scalars().all()
        products_by_id = {p.id: p for p in prods}

    batches_by_id: dict = {}
    if movements:
        batch_ids = {m.batch_id for m in movements}
        batches = (await db.execute(select(BatchORM).where(BatchORM.id.in_(batch_ids)))).scalars().all()
        batches_by_id = {b.id: b for b in batches}

    ref_numbers_by_id: dict = {}
    for ref_type, (orm_cls, number_col, _path) in _REFERENCE_LOOKUPS.items():
        ref_ids = {m.reference_id for m in movements if m.reference_type == ref_type and m.reference_id}
        if not ref_ids:
            continue
        rows = (await db.execute(select(orm_cls).where(orm_cls.id.in_(ref_ids)))).scalars().all()
        for row in rows:
            ref_numbers_by_id[row.id] = getattr(row, number_col)

    return {
        "data": [
            _movement_response(
                m, products_by_id.get(m.product_id), batches_by_id.get(m.batch_id),
                ref_numbers_by_id.get(m.reference_id))
            for m in movements
        ],
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "has_next": page * page_size < total, "has_prev": page > 1,
        },
    }
