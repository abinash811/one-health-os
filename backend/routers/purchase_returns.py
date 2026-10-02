from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.products import Product as ProductORM, StockBatch as BatchORM, StockMovement as MovementORM
from models.purchases import (
    Purchase as PurchaseORM,
    PurchaseItem as PurchaseItemORM,
    PurchaseReturn as PurchaseReturnORM,
    PurchaseReturnItem as PurchaseReturnItemORM,
)
from models.suppliers import Supplier as SupplierORM
from models.users import AuditLog
from routers.auth_helpers import User, get_current_user, get_owned_or_404, has_permission

router = APIRouter(prefix="/api", tags=["purchase_returns"])


# ── Pydantic request models ──────────────────────────────────────────────────

class PurchaseReturnItemCreate(BaseModel):
    product_sku: str
    product_name: str
    batch_id: Optional[str] = None
    batch_no: Optional[str] = None
    expiry_date: Optional[str] = None
    expiry: Optional[str] = None
    mrp: Optional[float] = None
    ptr: Optional[float] = None
    gst_percent: Optional[float] = 5
    qty_units: Optional[int] = None
    return_qty_units: Optional[int] = None
    cost_price_per_unit: Optional[float] = None
    reason: Optional[str] = None


class PurchaseReturnCreate(BaseModel):
    supplier_id: str
    purchase_id: str
    return_date: str
    items: List[PurchaseReturnItemCreate]
    note: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None
    payment_type: Optional[str] = "credit"


class PurchaseReturnUpdate(BaseModel):
    note: Optional[str] = None
    items: Optional[List[PurchaseReturnItemCreate]] = None
    edit_type: str = "non_financial"


class PurchaseReturnCreditUpdate(BaseModel):
    # The pharmacist enters the one real number they actually know — how
    # much the distributor has credited so far — rather than picking a
    # status from a dropdown that could drift out of sync with it.
    # `rejected` is the one thing that number alone can't express: the
    # distributor said no to what's left, not "hasn't gotten to it yet."
    credit_received: float = 0
    rejected: bool = False


# ── helpers ───────────────────────────────────────────────────────────────────

async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    # Mirrors purchases.py's identical helper — this router never logged
    # anything at all before, despite create/financial-edit both mutating
    # real stock and generating a debit note. No cross-router import
    # exists anywhere else in this codebase (each router defines its own
    # small local helpers), so this stays local rather than becoming the
    # first one. old_values/ip_address were added Sep 12, 2026 — same gap
    # as purchases.py/billing.py's own copies of this helper.
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _require_purchases_permission(current_user: User, action: str, db: AsyncSession) -> None:
    # Purchase Returns shares the "purchases" permission key with the
    # purchases module — there's no separate "purchase_returns" key
    # anywhere in the seeded role data, and the frontend treats Purchases/
    # Purchase Returns as one PageTabs unit under a single nav item, so
    # splitting the permission would only create a gap no role's
    # permissions dict actually covers.
    if not await has_permission(current_user, f"purchases:{action}", db):
        raise HTTPException(
            status_code=403,
            detail=f"Your role does not have permission to {action} purchase returns")


async def _generate_return_number(pharmacy_id: uuid.UUID, db: AsyncSession) -> str:
    # MAX() on the numeric suffix, cast in SQL — see the identical fix (and
    # its reasoning) in purchases.py's _generate_purchase_number. Same
    # broken ORDER BY-on-a-padded-string pattern, same fix, Sep 19, 2026.
    current_year = datetime.now(timezone.utc).year
    prefix = f"PRET-{current_year}-"
    result = await db.execute(
        select(func.max(cast(func.split_part(PurchaseReturnORM.return_number, "-", 3), Integer)))
        .where(PurchaseReturnORM.pharmacy_id == pharmacy_id, PurchaseReturnORM.return_number.like(f"{prefix}%"))
    )
    last_num = result.scalar_one_or_none()
    new_num = (last_num or 0) + 1
    return f"{prefix}{new_num:04d}"


async def _generate_debit_number(pharmacy_id: uuid.UUID, db: AsyncSession) -> str:
    # A pharmacy returning goods to a supplier issues a debit note (reduces
    # what it owes the supplier) — a credit note is the reverse direction.
    # Was "SCRED-"/credit_note_number, matching sales_returns.py's genuinely
    # correct credit-note terminology by copy-paste, not by design.
    current_year = datetime.now(timezone.utc).year
    prefix = f"SDN-{current_year}-"
    result = await db.execute(
        select(func.max(cast(func.split_part(PurchaseReturnORM.debit_note_number, "-", 3), Integer)))
        .where(PurchaseReturnORM.pharmacy_id == pharmacy_id, PurchaseReturnORM.debit_note_number.like(f"{prefix}%"))
    )
    last_num = result.scalar_one_or_none()
    new_num = (last_num or 0) + 1
    return f"{prefix}{new_num:04d}"


def _return_response(r: PurchaseReturnORM,
                     items: list[PurchaseReturnItemORM], supplier_name: str = "") -> dict:
    return {
        "id": str(r.id),
        "return_number": r.return_number,
        "supplier_id": str(r.supplier_id),
        "supplier_name": supplier_name,
        "purchase_id": str(r.purchase_id),
        "return_date": r.return_date.isoformat() if r.return_date else None,
        "status": r.status,
        "reason": r.return_reason,
        "payment_type": r.payment_type,
        "ptr_total": r.subtotal_paise / 100,
        "gst_amount": r.total_gst_paise / 100,
        "total_value": r.grand_total_paise / 100,
        "credit_status": r.credit_status,
        "credit_received": r.credit_received_paise / 100,
        "credit_owed": (r.grand_total_paise - r.credit_received_paise) / 100,
        "note": r.notes,
        "debit_note_number": r.debit_note_number,
        "items": [_return_item_response(i) for i in items],
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _return_item_response(i: PurchaseReturnItemORM) -> dict:
    return {
        "id": str(i.id),
        "product_id": str(i.product_id),
        "product_name": i.product_name,
        "batch_id": str(i.batch_id),
        "batch_no": i.batch_number,
        "expiry_date": i.expiry_date.isoformat() if i.expiry_date else None,
        "qty_units": i.quantity,
        "cost_price_per_unit": i.cost_price_paise / 100,
        "gst_percent": float(i.gst_rate),
        "line_total": i.line_total_paise / 100,
        "line_gst": i.gst_amount_paise / 100,
    }


async def _find_batch(pharmacy_id: uuid.UUID, product_id: uuid.UUID, batch_id: str |
                      None, batch_no: str | None, db: AsyncSession) -> BatchORM | None:
    """Find a batch by ID or by product+batch_number.

    No longer falls back to "any batch for this product with stock" when
    neither matches — that could silently deduct from a different batch
    than the one actually being returned, breaking the batch-level
    traceability Schedule H1 depends on. Callers already raise a 404 on
    None (the real UI always sends a real batch_id from the original
    purchase item, so this path isn't exercised by any current screen).
    """
    if batch_id:
        try:
            result = await db.execute(select(BatchORM).where(
                BatchORM.id == uuid.UUID(batch_id), BatchORM.pharmacy_id == pharmacy_id))
            batch = result.scalar_one_or_none()
            if batch:
                return batch
        except ValueError:
            pass
    if batch_no:
        result = await db.execute(
            select(BatchORM).where(
                BatchORM.pharmacy_id == pharmacy_id,
                BatchORM.product_id == product_id,
                BatchORM.batch_number == batch_no)
        )
        batch = result.scalar_one_or_none()
        if batch:
            return batch
    return None


async def _deduct_stock_and_record(
    batch: BatchORM, qty_units: int, product: ProductORM,
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, ref_id: uuid.UUID,
    reason: str, db: AsyncSession,
) -> None:
    """Deduct stock from batch and record a stock movement.

    Raises rather than silently skipping when stock is insufficient — a
    return that can't physically be deducted must not still issue a
    credit note, since that leaves the financial record and real stock
    disagreeing with nobody told. Same message pattern as billing.py's
    _deduct_stock_and_record insufficient-stock check.
    """
    # qty_units is already in real units, same as quantity_on_hand — see
    # models/products.py's StockBatch comment (migration a343c922f896).
    old_qty = batch.quantity_on_hand

    if old_qty < qty_units:
        raise HTTPException(
            status_code=400,
            detail=(f"Insufficient stock for {product.name} in batch {batch.batch_number}: "
                    f"{old_qty} available, {qty_units} requested"))

    batch.quantity_on_hand = old_qty - qty_units
    batch.quantity_returned = (batch.quantity_returned or 0) + qty_units

    db.add(MovementORM(
        pharmacy_id=pharmacy_id, product_id=product.id, batch_id=batch.id,
        movement_type="purchase_return", quantity=-qty_units,
        quantity_before=old_qty, quantity_after=batch.quantity_on_hand,
        reference_type="purchase_return", reference_id=ref_id,
        user_id=user_id, notes=reason,
    ))


# ── /purchases/{purchase_id}/items-for-return ──────────────────────────────────

@router.get("/purchases/{purchase_id}/items-for-return")
async def get_purchase_items_for_return(purchase_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    pid = uuid.UUID(purchase_id)
    purchase = await get_owned_or_404(
        db, PurchaseORM, pid, uuid.UUID(current_user.pharmacy_id), not_found_detail="Purchase not found")

    # Get purchase items
    items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == pid))
    purchase_items = items_result.scalars().all()

    # Get already-returned quantities from confirmed returns
    existing_returns = await db.execute(
        select(PurchaseReturnORM).where(
            PurchaseReturnORM.purchase_id == pid,
            PurchaseReturnORM.status == "confirmed")
    )
    return_ids = [r.id for r in existing_returns.scalars().all()]

    returned_qtys: dict[uuid.UUID, int] = {}  # product_id -> qty returned
    if return_ids:
        ret_items_result = await db.execute(
            select(PurchaseReturnItemORM).where(
                PurchaseReturnItemORM.purchase_return_id.in_(return_ids))
        )
        for ri in ret_items_result.scalars().all():
            key = ri.product_id
            returned_qtys[key] = returned_qtys.get(key, 0) + ri.quantity

    # Get supplier name
    sup_result = await db.execute(select(SupplierORM.name).where(
        SupplierORM.id == purchase.supplier_id))  # tenant-safe: purchase already scoped via get_owned_or_404
    supplier_name = sup_result.scalar_one_or_none() or ""

    # PurchaseItem only stores product_id (its real FK) — product_sku is a
    # request/response-only convenience. This endpoint hardcoded it to ""
    # forever (found Sep 13, 2026, Purchases product-review, live-testing
    # the one real Purchase Return entry point): create_purchase_return
    # looks a product up by this exact sku, so every real return via this
    # screen 404'd or 422'd — the same class of bug already fixed in
    # purchases.py's own _get_product_skus() on Aug 22, 2026, just never
    # ported to this sibling endpoint.
    product_ids = {item.product_id for item in purchase_items}
    sku_result = await db.execute(select(ProductORM.id, ProductORM.sku).where(ProductORM.id.in_(product_ids)))
    product_skus = {pid: sku for pid, sku in sku_result.all()}

    items_for_return = []
    for item in purchase_items:
        already_returned = returned_qtys.get(item.product_id, 0)
        original_qty = item.quantity_ordered
        items_for_return.append({
            "product_id": str(item.product_id),
            "product_name": item.product_name,
            "product_sku": product_skus.get(item.product_id, ""),
            "batch_id": str(item.batch_id) if item.batch_id else None,
            "batch_no": item.batch_number,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            "mrp": item.mrp_paise / 100,
            "ptr": item.cost_price_paise / 100,
            "gst_percent": float(item.gst_rate),
            "original_qty": original_qty,
            "already_returned_qty": already_returned,
            "max_returnable_qty": max(0, original_qty - already_returned),
        })

    return {
        "purchase_id": purchase_id,
        "purchase_number": purchase.purchase_number,
        "supplier_id": str(purchase.supplier_id),
        "supplier_name": supplier_name,
        "purchase_date": purchase.purchase_date.isoformat() if purchase.purchase_date else None,
        "invoice_no": purchase.supplier_invoice_number,
        "items": items_for_return,
    }


# ── /purchase-returns ──────────────────────────────────────────────────────────

@router.post("/purchase-returns")
async def create_purchase_return(return_data: PurchaseReturnCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_purchases_permission(current_user, "create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    supplier_id = uuid.UUID(return_data.supplier_id)
    purchase_id = uuid.UUID(return_data.purchase_id)

    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, pharmacy_id, not_found_detail="Supplier not found")

    original_purchase = None
    try:
        original_purchase = await get_owned_or_404(db, PurchaseORM, purchase_id, pharmacy_id)
    except HTTPException:
        pass  # matches this endpoint's existing "not found -> skip validation" contract

    # Validate return quantities against original purchase. Keyed by
    # product_id, not product_name — two different products could share
    # a display name (no uniqueness constraint on Product.name), which
    # would silently apply this check to the wrong line or double-count
    # across same-named products.
    if original_purchase:
        pur_items_result = await db.execute(select(PurchaseItemORM).where(PurchaseItemORM.purchase_id == purchase_id))
        pur_items = pur_items_result.scalars().all()
        original_qtys: dict[uuid.UUID, int] = {}
        for pi in pur_items:
            original_qtys[pi.product_id] = original_qtys.get(pi.product_id, 0) + pi.quantity_ordered

        # Get already returned
        existing_returns = await db.execute(
            select(PurchaseReturnORM).where(
                PurchaseReturnORM.purchase_id == purchase_id,
                PurchaseReturnORM.status == "confirmed")
        )
        return_ids = [r.id for r in existing_returns.scalars().all()]
        returned_qtys: dict[uuid.UUID, int] = {}
        if return_ids:
            ret_items_result = await db.execute(
                select(PurchaseReturnItemORM).where(
                    PurchaseReturnItemORM.purchase_return_id.in_(return_ids))
            )
            for ri in ret_items_result.scalars().all():
                returned_qtys[ri.product_id] = returned_qtys.get(ri.product_id, 0) + ri.quantity

        for item_data in return_data.items:
            qty_units = item_data.return_qty_units or item_data.qty_units or 0
            prod_result = await db.execute(
                select(ProductORM).where(
                    ProductORM.pharmacy_id == pharmacy_id,
                    ProductORM.sku == item_data.product_sku)
            )
            prod = prod_result.scalar_one_or_none()
            if not prod:
                raise HTTPException(status_code=404,
                                    detail=f"Product {item_data.product_sku} not found")
            max_returnable = original_qtys.get(prod.id, 0) - returned_qtys.get(prod.id, 0)
            if qty_units > max_returnable:
                raise HTTPException(
                    status_code=400,
                    detail=(f"Return qty ({qty_units}) exceeds max returnable "
                            f"({max_returnable}) for {item_data.product_name}"),
                )

    return_number = await _generate_return_number(pharmacy_id, db)
    # A return has always been created already-"confirmed" (deducts
    # stock in this same request, see below) — its debit note number
    # belongs right here, not behind a separate confirm step that never
    # existed in the real UI. Generating it after return_number so both
    # sequence numbers are assigned together.
    debit_number = await _generate_debit_number(pharmacy_id, db)
    reason = return_data.reason or "return"

    # Create return header
    subtotal_paise = 0
    gst_paise = 0
    item_orms: list[PurchaseReturnItemORM] = []

    for item_data in return_data.items:
        qty_units = item_data.return_qty_units or item_data.qty_units or 0
        if qty_units <= 0:
            continue

        ptr = item_data.ptr or item_data.cost_price_per_unit or 0
        gst_percent = item_data.gst_percent or 5
        cost_paise = int(ptr * 100)
        line_taxable = qty_units * cost_paise
        line_gst = int(line_taxable * gst_percent / 100)
        line_total = line_taxable + line_gst

        product = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == pharmacy_id,
                ProductORM.sku == item_data.product_sku)
        )
        product_orm = product.scalar_one_or_none()
        if not product_orm:
            raise HTTPException(status_code=404,
                                detail=f"Product {item_data.product_sku} not found")

        batch = await _find_batch(pharmacy_id, product_orm.id, item_data.batch_id, item_data.batch_no, db)
        if not batch:
            raise HTTPException(status_code=404,
                                detail=f"No batch found for {item_data.product_name}")

        expiry = item_data.expiry_date or item_data.expiry
        item_orm = PurchaseReturnItemORM(
            product_id=product_orm.id,
            batch_id=batch.id,
            product_name=item_data.product_name,
            batch_number=batch.batch_number,
            expiry_date=date.fromisoformat(expiry[:10]) if expiry else batch.expiry_date,
            quantity=qty_units,
            cost_price_paise=cost_paise,
            gst_rate=gst_percent,
            gst_amount_paise=line_gst,
            line_total_paise=line_total,
        )
        item_orms.append((item_orm, batch, product_orm))
        subtotal_paise += line_taxable
        gst_paise += line_gst

    if not item_orms:
        raise HTTPException(status_code=400, detail="No valid return items")

    grand_total_paise = round((subtotal_paise + gst_paise) / 100) * 100

    purchase_return = PurchaseReturnORM(
        pharmacy_id=pharmacy_id,
        purchase_id=purchase_id,
        supplier_id=supplier_id,
        return_number=return_number,
        return_date=date.fromisoformat(return_data.return_date[:10]),
        return_reason=reason,
        payment_type=return_data.payment_type or "credit",
        subtotal_paise=subtotal_paise,
        total_gst_paise=gst_paise,
        grand_total_paise=grand_total_paise,
        status="confirmed",
        debit_note_number=debit_number,
        notes=return_data.note or return_data.notes,
        created_by=uuid.UUID(current_user.id),
    )
    db.add(purchase_return)
    await db.flush()

    # Save items, deduct stock, record movements
    final_items: list[PurchaseReturnItemORM] = []
    for item_orm, batch, product_orm in item_orms:
        item_orm.purchase_return_id = purchase_return.id
        db.add(item_orm)

        await _deduct_stock_and_record(
            batch, item_orm.quantity, product_orm,
            pharmacy_id, uuid.UUID(current_user.id), purchase_return.id,
            f"Purchase return - {reason}", db,
        )
        final_items.append(item_orm)

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "purchase_return", purchase_return.id,
        {"return_number": return_number, "debit_number": debit_number, "purchase_id": str(purchase_id),
         "total_value": grand_total_paise / 100, "reason": reason},
        db,
        ip_address=_client_ip(request),
    )
    await db.flush()

    return _return_response(purchase_return, final_items, supplier.name)


@router.get("/purchase-returns")
async def get_purchase_returns(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    supplier_id: Optional[str] = None, status: Optional[str] = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    query = select(PurchaseReturnORM).where(PurchaseReturnORM.pharmacy_id == pharmacy_id)

    if from_date:
        query = query.where(PurchaseReturnORM.return_date >= date.fromisoformat(from_date[:10]))
    if to_date:
        query = query.where(PurchaseReturnORM.return_date <= date.fromisoformat(to_date[:10]))
    if supplier_id:
        query = query.where(PurchaseReturnORM.supplier_id == uuid.UUID(supplier_id))
    if status:
        query = query.where(PurchaseReturnORM.status == status)

    result = await db.execute(query.order_by(PurchaseReturnORM.return_date.desc()).limit(1000))
    returns = result.scalars().all()

    # Gather supplier names and items
    supplier_ids = {r.supplier_id for r in returns}
    sup_result = await db.execute(select(SupplierORM).where(SupplierORM.id.in_(supplier_ids))) if supplier_ids else None
    supplier_map = {s.id: s.name for s in sup_result.scalars().all()} if sup_result else {}

    return_ids = [r.id for r in returns]
    items_by_return: dict[uuid.UUID, list] = {rid: [] for rid in return_ids}
    if return_ids:
        items_result = await db.execute(
            select(PurchaseReturnItemORM).where(
                PurchaseReturnItemORM.purchase_return_id.in_(return_ids))
        )
        for item in items_result.scalars().all():
            items_by_return[item.purchase_return_id].append(item)

    return [_return_response(r, items_by_return.get(
        r.id, []), supplier_map.get(r.supplier_id, "")) for r in returns]


@router.get("/purchase-returns/{return_id}")
async def get_purchase_return(return_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    rid = uuid.UUID(return_id)
    purchase_return = await get_owned_or_404(
        db, PurchaseReturnORM, rid, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Purchase return not found")

    items_result = await db.execute(select(PurchaseReturnItemORM).where(
        PurchaseReturnItemORM.purchase_return_id == rid))
    items = items_result.scalars().all()

    sup_result = await db.execute(select(SupplierORM.name).where(
        # tenant-safe: purchase_return already scoped via get_owned_or_404
        SupplierORM.id == purchase_return.supplier_id))
    supplier_name = sup_result.scalar_one_or_none() or ""

    return _return_response(purchase_return, items, supplier_name)


@router.put("/purchase-returns/{return_id}")
async def update_purchase_return(
        return_id: str,
        update_data: PurchaseReturnUpdate,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    await _require_purchases_permission(current_user, "edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    rid = uuid.UUID(return_id)

    purchase_return = await get_owned_or_404(
        db, PurchaseReturnORM, rid, pharmacy_id, not_found_detail="Purchase return not found")

    # Non-financial edit
    if update_data.edit_type == "non_financial":
        old_note = purchase_return.notes
        if update_data.note is not None:
            purchase_return.notes = update_data.note
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "update_non_financial", "purchase_return", rid,
            {"note": update_data.note}, db,
            old_values={"note": old_note}, ip_address=_client_ip(request),
        )
        await db.flush()
        await db.refresh(purchase_return)  # updated_at has onupdate=func.now() — see purchases.py

        items_result = await db.execute(select(PurchaseReturnItemORM).where(
            PurchaseReturnItemORM.purchase_return_id == rid))
        sup_result = await db.execute(select(SupplierORM.name).where(
            # tenant-safe: purchase_return already scoped via get_owned_or_404
            SupplierORM.id == purchase_return.supplier_id))
        return _return_response(purchase_return, items_result.scalars().all(),
                                sup_result.scalar_one_or_none() or "")

    # Financial edit — requires items
    if not update_data.items:
        raise HTTPException(status_code=400, detail="Items required for financial edit")

    # Get old items for stock adjustment
    old_items_result = await db.execute(select(PurchaseReturnItemORM).where(
        PurchaseReturnItemORM.purchase_return_id == rid))
    old_items = old_items_result.scalars().all()
    old_qty_map: dict[uuid.UUID, int] = {}  # product_id -> old qty
    for oi in old_items:
        old_qty_map[oi.product_id] = old_qty_map.get(oi.product_id, 0) + oi.quantity

    # Delete old items
    for oi in old_items:
        await db.delete(oi)
    await db.flush()

    # Rebuild items
    subtotal_paise = 0
    gst_paise = 0
    new_items: list[PurchaseReturnItemORM] = []

    for item_data in update_data.items:
        qty_units = item_data.return_qty_units or item_data.qty_units or 0
        if qty_units <= 0:
            continue

        ptr = item_data.ptr or item_data.cost_price_per_unit or 0
        gst_percent = item_data.gst_percent or 5
        cost_paise = int(ptr * 100)
        line_taxable = qty_units * cost_paise
        line_gst = int(line_taxable * gst_percent / 100)
        line_total = line_taxable + line_gst

        product = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == pharmacy_id,
                ProductORM.sku == item_data.product_sku)
        )
        product_orm = product.scalar_one_or_none()
        if not product_orm:
            continue

        batch = await _find_batch(pharmacy_id, product_orm.id, item_data.batch_id, item_data.batch_no, db)
        if not batch:
            continue

        expiry = item_data.expiry_date or item_data.expiry
        item_orm = PurchaseReturnItemORM(
            purchase_return_id=rid,
            product_id=product_orm.id,
            batch_id=batch.id,
            product_name=item_data.product_name,
            batch_number=batch.batch_number,
            expiry_date=date.fromisoformat(expiry[:10]) if expiry else batch.expiry_date,
            quantity=qty_units,
            cost_price_paise=cost_paise,
            gst_rate=gst_percent,
            gst_amount_paise=line_gst,
            line_total_paise=line_total,
        )
        db.add(item_orm)
        new_items.append(item_orm)
        subtotal_paise += line_taxable
        gst_paise += line_gst

        # Adjust stock for quantity difference
        old_qty = old_qty_map.get(product_orm.id, 0)
        qty_diff = qty_units - old_qty
        if qty_diff > 0:
            # More being returned now — deduct additional stock
            await _deduct_stock_and_record(
                batch, qty_diff, product_orm,
                pharmacy_id, uuid.UUID(current_user.id), rid,
                "Purchase return edit adjustment", db,
            )
        elif qty_diff < 0:
            # Less being returned — restore stock. abs(qty_diff) is already
            # in real units, same as quantity_on_hand (migration a343c922f896).
            restore_units = abs(qty_diff)
            old_qty_hand = batch.quantity_on_hand
            batch.quantity_on_hand = old_qty_hand + restore_units
            batch.quantity_returned = max(0, (batch.quantity_returned or 0) - restore_units)

            db.add(MovementORM(
                pharmacy_id=pharmacy_id, product_id=product_orm.id, batch_id=batch.id,
                movement_type="purchase_return_edit", quantity=abs(qty_diff),
                quantity_before=old_qty_hand, quantity_after=batch.quantity_on_hand,
                reference_type="purchase_return", reference_id=rid,
                user_id=uuid.UUID(current_user.id), notes="Purchase return edit - stock restored",
            ))

    grand_total_paise = round((subtotal_paise + gst_paise) / 100) * 100

    old_total_value = purchase_return.grand_total_paise / 100

    purchase_return.subtotal_paise = subtotal_paise
    purchase_return.total_gst_paise = gst_paise
    purchase_return.grand_total_paise = grand_total_paise
    if update_data.note is not None:
        purchase_return.notes = update_data.note

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update_financial", "purchase_return", rid,
        {"total_value": grand_total_paise / 100, "item_count": len(new_items)}, db,
        old_values={"total_value": old_total_value, "item_count": len(old_items)},
        ip_address=_client_ip(request),
    )
    await db.flush()
    await db.refresh(purchase_return)  # updated_at has onupdate=func.now() — see purchases.py

    # tenant-safe: purchase_return already scoped via get_owned_or_404
    sup_result = await db.execute(select(SupplierORM.name).where(SupplierORM.id == purchase_return.supplier_id))
    return _return_response(purchase_return, new_items, sup_result.scalar_one_or_none() or "")


@router.put("/purchase-returns/{return_id}/credit-status")
async def update_purchase_return_credit_status(
        return_id: str,
        body: PurchaseReturnCreditUpdate,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """Record how much of a return the distributor has actually credited
    so far — separate from `status` (the return record itself, which is
    "confirmed" the instant stock is deducted). A pharmacy returning
    expired/damaged stock doesn't get paid back immediately, and a
    distributor can credit less than what was sent back; without this,
    there was no way to know how much was still genuinely owed. Found
    Sep 13, 2026, Purchases product-review — the original spec assumed a
    live accept/reject workflow with the distributor as a participant in
    the system, which isn't realistic since distributors don't use
    PharmaCare; this tracks the same real business need (what's actually
    been paid back) from the pharmacy's own side instead.
    """
    await _require_purchases_permission(current_user, "edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    rid = uuid.UUID(return_id)

    purchase_return = await get_owned_or_404(
        db, PurchaseReturnORM, rid, pharmacy_id, not_found_detail="Purchase return not found")

    credit_received_paise = int(round(body.credit_received * 100))
    if credit_received_paise < 0:
        raise HTTPException(status_code=400, detail="Credit received cannot be negative")
    if credit_received_paise > purchase_return.grand_total_paise:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Credit received (₹{body.credit_received:.2f}) cannot exceed this return's "
                f"total value (₹{purchase_return.grand_total_paise / 100:.2f})"),
        )

    old_status = purchase_return.credit_status
    old_received = purchase_return.credit_received_paise

    purchase_return.credit_received_paise = credit_received_paise
    if body.rejected:
        purchase_return.credit_status = "rejected"
    elif credit_received_paise <= 0:
        purchase_return.credit_status = "pending"
    elif credit_received_paise < purchase_return.grand_total_paise:
        purchase_return.credit_status = "partially_credited"
    else:
        purchase_return.credit_status = "fully_credited"

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update_credit_status", "purchase_return", rid,
        {"credit_status": purchase_return.credit_status, "credit_received": body.credit_received},
        db,
        old_values={"credit_status": old_status, "credit_received": old_received / 100},
        ip_address=_client_ip(request),
    )
    await db.flush()
    await db.refresh(purchase_return)  # updated_at has onupdate=func.now() — see purchases.py

    items_result = await db.execute(select(PurchaseReturnItemORM).where(
        PurchaseReturnItemORM.purchase_return_id == rid))
    # tenant-safe: purchase_return already scoped via get_owned_or_404
    sup_result = await db.execute(select(SupplierORM.name).where(SupplierORM.id == purchase_return.supplier_id))
    return _return_response(purchase_return, items_result.scalars().all(), sup_result.scalar_one_or_none() or "")


# Note: there is no POST /purchase-returns/{id}/confirm endpoint. It
# existed until Aug 24, 2026 but was unreachable dead code —
# create_purchase_return already sets status="confirmed" and deducts
# stock in the same request (see below), so a separate confirm step
# was never exercised by any frontend screen or test. Removed rather
# than kept "for consistency"; see docs/15_ROADMAP.md's RULE MISSES LOG
# / KNOWN ISSUES for the removal note.
