from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.billing import Bill, BillItem, SalesReturn as SalesReturnORM, SalesReturnItem as SalesReturnItemORM
from models.pharmacy import PharmacySettings
from models.products import Product as ProductORM, StockBatch as BatchORM, StockMovement as MovementORM
from models.purchases import Purchase as PurchaseORM, PurchaseReturn as PurchaseReturnORM
from models.users import AuditLog
from services.role_scope import find_role, get_role_or_404
from routers.auth_helpers import User, get_current_user, get_owned_or_404, has_permission, require_admin_or_super

router = APIRouter(prefix="/api", tags=["sales_returns"])


# ── Pydantic request models ──────────────────────────────────────────────────

class SalesReturnItemCreate(BaseModel):
    medicine_id: Optional[str] = None
    medicine_name: str
    product_sku: Optional[str] = None
    batch_id: Optional[str] = None
    batch_no: str
    expiry_date: Optional[str] = None
    mrp: float
    qty: int
    original_qty: int
    disc_percent: float = 0
    disc_price: Optional[float] = None
    gst_percent: float = 5
    amount: Optional[float] = None
    is_damaged: bool = False


class SalesReturnCreate(BaseModel):
    original_bill_id: Optional[str] = None
    original_bill_no: Optional[str] = None
    return_date: str
    patient: Optional[Dict[str, Any]] = None
    doctor: Optional[str] = None
    items: List[SalesReturnItemCreate]
    payment_type: Optional[str] = None
    refund_method: str = "same_as_original"
    note: Optional[str] = None


class SalesReturnUpdate(BaseModel):
    doctor: Optional[str] = None
    note: Optional[str] = None
    items: Optional[List[SalesReturnItemCreate]] = None
    refund_method: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    # Mirrors billing.py/purchase_returns.py's identical local helper — no
    # cross-router import exists anywhere in this codebase, each router
    # keeps its own copy. This router never logged anything at all before
    # (Sep 15, 2026 product-review finding), despite create/financial-edit
    # both mutating real stock and, now, a due bill's balance.
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _resolve_refund_and_credit(
        requested_method: str, grand_total_paise: int, bill: Bill | None) -> tuple[str, int]:
    """Decide how much of a return credits the bill's due balance vs. is an
    actual cash/UPI refund, and what refund_method label to store.

    Always credits any outstanding balance on the bill first, regardless of
    the caller's requested method — a customer can't be handed cash for
    goods they never fully paid for (Sep 15, 2026 product-review: "Credit
    to Account" was previously a decorative dropdown option with zero real
    effect on what a customer owed). Shared by create and financial-edit so
    both resolve the exact same way.

    A return can exceed what was still owed (e.g. a due bill for ₹200 gets
    a ₹500 return) — the ₹200 still credits the balance, but the remaining
    ₹300 is a real refund, so refund_method describes that leftover, not
    the whole return.

    `bill` is None for a manual return (no original bill) — nothing to
    credit, and "same_as_original" has no original sale to fall back to.
    """
    if bill is None:
        resolved = "cash" if requested_method == "same_as_original" else requested_method
        return resolved, 0

    credit_paise = min(grand_total_paise, max(0, bill.balance_paise))
    excess_paise = grand_total_paise - credit_paise
    if excess_paise == 0 and credit_paise > 0:
        return "credit_to_account", credit_paise
    if requested_method == "same_as_original":
        # Nothing (or only part) left to credit — refund the rest however
        # the sale itself was settled. A "multiple" (Multi-payment split,
        # added Sep 16, 2026) original bill has no single method to copy —
        # falls back to cash, same as the bill-is-None case above, rather
        # than storing the meaningless literal "multiple" as a refund
        # method REFUND_METHOD doesn't even define.
        original_method = bill.payment_method if bill.payment_method != "multiple" else None
        return (original_method or "cash"), credit_paise
    return requested_method, credit_paise


async def _generate_credit_note_number(pharmacy_id: uuid.UUID, db: AsyncSession) -> str:
    # Configurable prefix/length via Settings > Bill Sequence (Sales Return),
    # stored as an atomic counter on PharmacySettings — same pattern as
    # billing.py's _generate_bill_number, and for the same reason: deriving
    # the next number from MAX(return_number) races under concurrent inserts.
    result = await db.execute(
        select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id)
    )
    ps = result.scalar_one_or_none()

    prefix = ps.return_prefix if ps else "CN"
    length = ps.return_number_length if ps else 5
    seq = ps.return_sequence_number if ps else 1

    return_number = f"{prefix}-{str(seq).zfill(length)}"

    if ps:
        ps.return_sequence_number = seq + 1
    else:
        ps = PharmacySettings(pharmacy_id=pharmacy_id, return_sequence_number=2)
        db.add(ps)

    return return_number


def _return_response(
        r: SalesReturnORM, items: list[SalesReturnItemORM], bill: Bill | None = None) -> dict:
    item_list = []
    for i in items:
        sale_price = i.sale_price_paise / 100
        gst_percent = float(i.gst_rate)
        disc_percent = 0  # stored at bill-item level, not on return item
        line_total = i.line_total_paise / 100

        item_list.append({
            "id": str(i.id),
            "medicine_name": i.product_name,
            "product_id": str(i.product_id),
            "batch_id": str(i.batch_id),
            "batch_no": i.batch_number,
            "mrp": sale_price,
            "qty": i.quantity,
            "original_qty": 0,
            "disc_percent": disc_percent,
            "gst_percent": gst_percent,
            "amount": line_total,
            "is_damaged": not i.return_to_stock,
        })

    return {
        "id": str(r.id),
        "return_no": r.return_number,
        "original_bill_id": str(r.original_bill_id) if r.original_bill_id else None,
        "original_bill_no": bill.bill_number if bill else None,
        "return_date": r.return_date.isoformat() if r.return_date else None,
        "status": r.status,
        "mrp_total": r.total_paise / 100,
        "gst_amount": r.total_gst_paise / 100,
        "net_amount": r.grand_total_paise / 100,
        "refund_method": r.refund_method,
        "credit_applied": r.credit_applied_paise / 100,
        "note": r.notes,
        "items": item_list,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


async def _find_batch(
        pharmacy_id: uuid.UUID,
        product_id: uuid.UUID | None,
        batch_id: str | None,
        batch_no: str | None,
        db: AsyncSession) -> BatchORM | None:
    if batch_id:
        try:
            result = await db.execute(select(BatchORM).where(
                BatchORM.id == uuid.UUID(batch_id), BatchORM.pharmacy_id == pharmacy_id))
            batch = result.scalar_one_or_none()
            if batch:
                return batch
        except ValueError:
            pass
    if product_id and batch_no:
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


async def _find_bill_item(bill_id: uuid.UUID, product_id: uuid.UUID,
                          batch_id: uuid.UUID, db: AsyncSession) -> BillItem | None:
    result = await db.execute(
        select(BillItem).where(
            BillItem.bill_id == bill_id,
            BillItem.product_id == product_id,
            BillItem.batch_id == batch_id,
        )
    )
    return result.scalar_one_or_none()


async def _restore_stock(
    batch: BatchORM, qty_units: int, product: ProductORM, return_to_stock: bool,
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, ref_id: uuid.UUID,
    reason: str, db: AsyncSession,
) -> None:
    # qty_units is already in real units, same as quantity_on_hand — see
    # models/products.py's StockBatch comment (migration a343c922f896).
    old_qty = batch.quantity_on_hand

    if return_to_stock:
        batch.quantity_on_hand = old_qty + qty_units
    batch.quantity_returned = (batch.quantity_returned or 0) + qty_units

    db.add(MovementORM(
        pharmacy_id=pharmacy_id, product_id=product.id, batch_id=batch.id,
        movement_type="sales_return", quantity=qty_units,
        quantity_before=old_qty, quantity_after=batch.quantity_on_hand,
        reference_type="sales_return", reference_id=ref_id,
        user_id=user_id, notes=reason,
    ))


async def _reverse_stock(
    batch: BatchORM, qty_units: int, product: ProductORM, was_return_to_stock: bool,
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, ref_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Reverse a previous stock restoration (for financial edits)."""
    old_qty = batch.quantity_on_hand

    if was_return_to_stock:
        batch.quantity_on_hand = max(0, old_qty - qty_units)
    batch.quantity_returned = max(0, (batch.quantity_returned or 0) - qty_units)

    db.add(MovementORM(
        pharmacy_id=pharmacy_id, product_id=product.id, batch_id=batch.id,
        movement_type="sales_return_reversal", quantity=-qty_units,
        quantity_before=old_qty, quantity_after=batch.quantity_on_hand,
        reference_type="sales_return", reference_id=ref_id,
        user_id=user_id, notes="Sales return financial edit - stock reversal",
    ))


# ── /sales-returns ─────────────────────────────────────────────────────────────

@router.post("/sales-returns")
async def create_sales_return(return_data: SalesReturnCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # permission-exempt: removing the allow_manual_returns check (Sep 23,
    # 2026, see the original_bill_id block below) exposed that it was the
    # ONLY permission check this endpoint ever had — the normal bill-linked
    # path below has never been role-gated, for any role. Same class of gap
    # as Billing's 4 money endpoints (docs/15_ROADMAP.md) and the same
    # standing decision: leave as-is, do not add ACL here now, revisit
    # post-launch based on real usage rather than a guess made before launch.
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    user_id = uuid.UUID(current_user.id)

    ps_result = await db.execute(
        select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = ps_result.scalar_one_or_none()
    return_window_days = ps.return_window_days if ps else 7
    allow_partial_return = ps.allow_partial_return if ps else True

    original_bill: Bill | None = None
    bill_id: uuid.UUID | None = None
    bill_items: list[BillItem] = []
    bill_items_by_batch: dict[str, BillItem] = {}

    # A return with no original bill (previously gated behind the
    # allow_manual_returns permission + the "Require original bill" Settings
    # toggle) is a real fraud/leakage surface — nothing ties the returned
    # quantity or refund amount to an actual prior sale. Removed Sep 23,
    # 2026, direct product decision: every return must now originate from a
    # real bill, unconditionally, for every role including admin. The
    # PharmacySettings.require_original_bill column and the
    # allow_manual_returns permission are left in the schema (harmless,
    # unread) rather than migrated out — see docs/15_ROADMAP.md.
    if not return_data.original_bill_id:
        raise HTTPException(
            status_code=400,
            detail="A return must be created from an existing bill — open the bill and use its Return option.",
        )
    else:
        original_bill = await get_owned_or_404(
            db, Bill, return_data.original_bill_id, pharmacy_id, not_found_detail="Original bill not found")
        bill_id = original_bill.id

        # Settings → Returns "Return window (days)" — found Sep 13, 2026
        # (Settings product-review): saved but never checked against the
        # original bill's age, so a return could be filed for a sale from
        # years ago regardless of what the pharmacy configured.
        if original_bill.created_at:
            bill_age_days = (date.today() - original_bill.created_at.date()).days
            if bill_age_days > return_window_days:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"This bill is {bill_age_days} days old — returns are only allowed within "
                        f"{return_window_days} days (Settings → Returns)."
                    ),
                )

        # Get original bill items for validation
        bill_items_result = await db.execute(select(BillItem).where(BillItem.bill_id == bill_id))
        bill_items = bill_items_result.scalars().all()
        bill_items_by_batch = {bi.batch_number: bi for bi in bill_items}

        # Cap against what's actually still returnable, not just the
        # original sale total — found Sep 23, 2026 (direct question,
        # "can a user return more than they sold"): this only ever checked
        # the new request against the original bill quantity, never against
        # quantity already returned in an earlier, separate return on this
        # same bill — two returns could each claim the full original
        # quantity and both would pass. purchase_returns.py's
        # create_purchase_return already solves the identical problem
        # (already_returned_qty / max_returnable_qty) — this ports the same
        # pattern here.
        prior_returns_result = await db.execute(
            select(SalesReturnItemORM.batch_number, SalesReturnItemORM.quantity)
            .join(SalesReturnORM, SalesReturnItemORM.sales_return_id == SalesReturnORM.id)
            .where(SalesReturnORM.original_bill_id == bill_id)
        )
        already_returned_by_batch: dict[str, int] = {}
        for batch_number, qty in prior_returns_result.all():
            already_returned_by_batch[batch_number] = already_returned_by_batch.get(batch_number, 0) + qty

        for item in return_data.items:
            orig_item = bill_items_by_batch.get(item.batch_no)
            if orig_item:
                already_returned = already_returned_by_batch.get(item.batch_no, 0)
                max_returnable = orig_item.quantity - already_returned
                if item.qty > max_returnable:
                    raise HTTPException(
                        status_code=400,
                        detail=(f"Return quantity for {item.medicine_name} ({item.qty}) exceeds "
                                f"the remaining returnable quantity ({max_returnable}) — "
                                f"{already_returned} of {orig_item.quantity} already returned."),
                    )

        # Settings → Returns "Allow partial returns" — found Sep 13, 2026
        # (Settings product-review): saved but never enforced, so a return for
        # only some of a bill's items always succeeded regardless of the
        # toggle. When off, every item on the original bill must be returned
        # in full. Meaningless without an original bill, so only checked here.
        if not allow_partial_return:
            returned_batches = {item.batch_no: item.qty for item in return_data.items}
            for bi in bill_items:
                if returned_batches.get(bi.batch_number, 0) != bi.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Partial returns are disabled (Settings → Returns) — "
                            "the full quantity of every item on the original bill must be returned."
                        ),
                    )

    return_no = await _generate_credit_note_number(pharmacy_id, db)

    # Calculate totals
    total_paise = 0
    gst_paise = 0
    item_orms: list[tuple[SalesReturnItemORM, BatchORM, ProductORM]] = []

    for item_data in return_data.items:
        sale_price_paise = int(item_data.mrp * 100)
        base_paise = sale_price_paise * item_data.qty
        disc_paise = int(base_paise * item_data.disc_percent / 100)
        after_disc_paise = base_paise - disc_paise
        line_gst_paise = int(after_disc_paise * item_data.gst_percent / 100)
        line_total_paise = after_disc_paise + line_gst_paise

        # Resolve product
        product_id: uuid.UUID | None = None
        product: ProductORM | None = None
        if item_data.product_sku:
            prod_result = await db.execute(
                select(ProductORM).where(
                    ProductORM.pharmacy_id == pharmacy_id,
                    ProductORM.sku == item_data.product_sku)
            )
            product = prod_result.scalar_one_or_none()
            if product:
                product_id = product.id
        if not product_id and item_data.medicine_id:
            try:
                prod_result = await db.execute(select(ProductORM).where(
                    ProductORM.id == uuid.UUID(item_data.medicine_id),
                    ProductORM.pharmacy_id == pharmacy_id))
                product = prod_result.scalar_one_or_none()
                if product:
                    product_id = product.id
            except ValueError:
                pass
        # Fallback: find product from bill item
        if not product_id:
            bi = bill_items_by_batch.get(item_data.batch_no)
            if bi:
                product_id = bi.product_id
                prod_result = await db.execute(select(ProductORM).where(
                    ProductORM.id == product_id, ProductORM.pharmacy_id == pharmacy_id))
                product = prod_result.scalar_one_or_none()

        if not product_id or not product:
            raise HTTPException(status_code=404,
                                detail=f"Product not found for {item_data.medicine_name}")

        # Marked non-returnable in Inventory (e.g. a narcotic, or an
        # opened/loose-sold item) — added Sep 19, 2026, Abinash direct
        # instruction: a real block, not just a warning.
        if not product.is_returnable:
            raise HTTPException(
                status_code=400,
                detail=f"{product.name} is marked as non-returnable and cannot be included in a sales return.")

        batch = await _find_batch(pharmacy_id, product_id, item_data.batch_id, item_data.batch_no, db)
        if not batch:
            raise HTTPException(status_code=404,
                                detail=f"Batch not found for {item_data.medicine_name}")

        # Find the matching bill_item for the FK — only when this return is
        # actually tied to a bill. A manual return has none to link.
        bill_item_id: uuid.UUID | None = None
        if bill_id:
            bill_item = await _find_bill_item(bill_id, product_id, batch.id, db)
            if not bill_item:
                # Fallback: find by batch_number
                bi_result = await db.execute(
                    select(BillItem).where(
                        BillItem.bill_id == bill_id,
                        BillItem.batch_number == item_data.batch_no)
                )
                bill_item = bi_result.scalar_one_or_none()
            if not bill_item:
                raise HTTPException(status_code=400,
                                    detail=f"No matching bill item found for {item_data.medicine_name}")
            bill_item_id = bill_item.id

        return_to_stock = not item_data.is_damaged

        item_orm = SalesReturnItemORM(
            bill_item_id=bill_item_id,
            product_id=product_id,
            batch_id=batch.id,
            product_name=item_data.medicine_name,
            batch_number=item_data.batch_no,
            quantity=item_data.qty,
            sale_price_paise=sale_price_paise,
            gst_rate=item_data.gst_percent,
            gst_paise=line_gst_paise,
            line_total_paise=line_total_paise,
            return_to_stock=return_to_stock,
        )
        item_orms.append((item_orm, batch, product))
        total_paise += after_disc_paise
        gst_paise += line_gst_paise

    if not item_orms:
        raise HTTPException(status_code=400, detail="No valid return items")

    grand_total_paise = round((total_paise + gst_paise) / 100) * 100

    return_date_val = date.fromisoformat(return_data.return_date[:10])

    resolved_refund_method, credit_to_balance_paise = _resolve_refund_and_credit(
        return_data.refund_method, grand_total_paise, original_bill)

    sales_return = SalesReturnORM(
        pharmacy_id=pharmacy_id,
        original_bill_id=bill_id,
        return_number=return_no,
        return_date=return_date_val,
        return_reason=return_data.note,
        total_paise=total_paise,
        total_gst_paise=gst_paise,
        grand_total_paise=grand_total_paise,
        refund_method=resolved_refund_method,
        credit_applied_paise=credit_to_balance_paise,
        status="completed",
        notes=return_data.note,
        created_by=user_id,
    )
    db.add(sales_return)
    await db.flush()

    # Save items and restore stock
    final_items: list[SalesReturnItemORM] = []
    for item_orm, batch, product in item_orms:
        item_orm.sales_return_id = sales_return.id
        db.add(item_orm)

        reason = "Sales return" + (" (damaged)" if not item_orm.return_to_stock else "")
        await _restore_stock(
            batch, item_orm.quantity, product, item_orm.return_to_stock,
            pharmacy_id, user_id, sales_return.id, reason, db,
        )
        final_items.append(item_orm)

    ip = _client_ip(request)
    await _record_audit(
        pharmacy_id, user_id, "create", "sales_return", sales_return.id,
        {"return_number": return_no,
         "original_bill_no": original_bill.bill_number if original_bill else None,
         "net_amount": grand_total_paise / 100, "refund_method": resolved_refund_method,
         "credit_applied": credit_to_balance_paise / 100},
        db, ip_address=ip,
    )

    if credit_to_balance_paise > 0:
        old_balance = original_bill.balance_paise / 100
        old_paid = original_bill.amount_paid_paise / 100
        old_status = original_bill.status

        original_bill.amount_paid_paise += credit_to_balance_paise
        original_bill.balance_paise = max(
            0, original_bill.grand_total_paise - original_bill.amount_paid_paise)
        if original_bill.balance_paise <= 0:
            original_bill.status = "paid"

        # A distinct action ("return_credit", not "payment") so Day-End
        # Closing's cash-drawer reconciliation — which reads AuditLog rows
        # scoped to action in ("create", "payment") — never mistakes a
        # returned-goods credit for real cash collected that day.
        await _record_audit(
            pharmacy_id, user_id, "return_credit", "invoice", bill_id,
            {"paid_amount": original_bill.amount_paid_paise / 100,
             "due_amount": original_bill.balance_paise / 100, "status": original_bill.status,
             "return_number": return_no},
            db,
            old_values={"paid_amount": old_paid, "due_amount": old_balance, "status": old_status},
            ip_address=ip,
        )

    await db.flush()

    return _return_response(sales_return, final_items, original_bill)


@router.get("/sales-returns")
async def get_sales_returns(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    search: Optional[str] = None, payment_type: Optional[str] = None,
    page: int = 1, page_size: int = 50,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    query = select(SalesReturnORM).where(SalesReturnORM.pharmacy_id == pharmacy_id)

    if from_date:
        query = query.where(SalesReturnORM.return_date >= date.fromisoformat(from_date[:10]))
    if to_date:
        query = query.where(SalesReturnORM.return_date <= date.fromisoformat(to_date[:10]))
    if payment_type and payment_type != "all":
        query = query.where(SalesReturnORM.refund_method == payment_type)
    if search:
        p = f"%{search}%"
        query = query.where(or_(
            SalesReturnORM.return_number.ilike(p),
            SalesReturnORM.notes.ilike(p),
        ))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(SalesReturnORM.created_at.desc()).offset(offset).limit(page_size))
    returns = result.scalars().all()

    # Gather items and bills
    return_ids = [r.id for r in returns]
    items_by_return: dict[uuid.UUID, list] = {rid: [] for rid in return_ids}
    if return_ids:
        items_result = await db.execute(
            select(SalesReturnItemORM).where(SalesReturnItemORM.sales_return_id.in_(return_ids))
        )
        for item in items_result.scalars().all():
            items_by_return[item.sales_return_id].append(item)

    bill_ids = {r.original_bill_id for r in returns if r.original_bill_id}
    bill_map: dict[uuid.UUID, Bill] = {}
    if bill_ids:
        bills_result = await db.execute(select(Bill).where(Bill.id.in_(bill_ids)))
        bill_map = {b.id: b for b in bills_result.scalars().all()}

    data = [
        _return_response(r, items_by_return.get(r.id, []), bill_map.get(r.original_bill_id))
        for r in returns
    ]

    # Today's stats
    today = date.today()
    today_result = await db.execute(
        select(func.count(), func.coalesce(func.sum(SalesReturnORM.grand_total_paise), 0))
        .where(SalesReturnORM.pharmacy_id == pharmacy_id, SalesReturnORM.return_date == today)
    )
    row = today_result.one()
    returns_today = row[0]
    total_refunded_today = row[1] / 100

    return {
        "data": data,
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "has_next": page * page_size < total, "has_prev": page > 1,
        },
        "stats": {"returns_today": returns_today, "total_refunded_today": total_refunded_today},
    }


@router.get("/sales-returns/{return_id}")
async def get_sales_return(return_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # Try by UUID first, then by return_number
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    sales_return: SalesReturnORM | None = None
    try:
        rid = uuid.UUID(return_id)
        result = await db.execute(select(SalesReturnORM).where(
            SalesReturnORM.id == rid, SalesReturnORM.pharmacy_id == pharmacy_id))
        sales_return = result.scalar_one_or_none()
    except ValueError:
        pass

    if not sales_return:
        result = await db.execute(select(SalesReturnORM).where(
            SalesReturnORM.return_number == return_id, SalesReturnORM.pharmacy_id == pharmacy_id))
        sales_return = result.scalar_one_or_none()

    if not sales_return:
        raise HTTPException(status_code=404, detail="Sales return not found")

    items_result = await db.execute(
        select(SalesReturnItemORM).where(SalesReturnItemORM.sales_return_id == sales_return.id)
    )
    items = items_result.scalars().all()

    # tenant-safe: sales_return already scoped
    bill_result = await db.execute(select(Bill).where(Bill.id == sales_return.original_bill_id))
    bill = bill_result.scalar_one_or_none()

    return _return_response(sales_return, items, bill)


@router.put("/sales-returns/{return_id}")
async def update_sales_return(
    return_id: str, update_data: SalesReturnUpdate, request: Request,
    financial_edit: bool = False,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    user_id = uuid.UUID(current_user.id)
    rid = uuid.UUID(return_id)
    ip = _client_ip(request)

    sales_return = await get_owned_or_404(
        db, SalesReturnORM, rid, pharmacy_id, not_found_detail="Sales return not found")

    if financial_edit and update_data.items:
        # has_permission() honors a "*"-wildcard ("Super Admin") custom role
        # the same way admin's own permissions list does — see the identical
        # fix on create_sales_return's allow_manual_returns check above.
        if not await has_permission(current_user, "allow_financial_edit_return", db):
            raise HTTPException(status_code=403, detail="Financial edit requires permission")

        # None for a manual return (no original bill) — _resolve_refund_and_
        # credit already treats that as "nothing to credit."
        original_bill: Bill | None = None
        if sales_return.original_bill_id:
            # tenant-safe: sales_return already scoped
            bill_result = await db.execute(select(Bill).where(Bill.id == sales_return.original_bill_id))
            original_bill = bill_result.scalar_one()

        # Reverse any credit this return previously applied to the bill's
        # due balance, before recalculating totals below — same
        # reverse-then-rebuild shape as the stock handling that follows.
        old_credit_applied = sales_return.credit_applied_paise
        if original_bill and old_credit_applied > 0:
            original_bill.amount_paid_paise = max(0, original_bill.amount_paid_paise - old_credit_applied)
            original_bill.balance_paise = max(
                0, original_bill.grand_total_paise - original_bill.amount_paid_paise)
            original_bill.status = "due" if original_bill.balance_paise > 0 else "paid"

        # Reverse old stock changes
        old_items_result = await db.execute(
            select(SalesReturnItemORM).where(SalesReturnItemORM.sales_return_id == rid)
        )
        old_items = old_items_result.scalars().all()

        for old_item in old_items:
            # tenant-safe: old_item is a child row of the already-scoped sales_return
            batch_result = await db.execute(select(BatchORM).where(BatchORM.id == old_item.batch_id))
            batch = batch_result.scalar_one_or_none()
            # tenant-safe: same as above
            prod_result = await db.execute(select(ProductORM).where(ProductORM.id == old_item.product_id))
            product = prod_result.scalar_one_or_none()
            if batch and product:
                await _reverse_stock(
                    batch, old_item.quantity, product, old_item.return_to_stock,
                    pharmacy_id, user_id, rid, db)

        # Delete old items
        for old_item in old_items:
            await db.delete(old_item)
        await db.flush()

        # Same remaining-returnable cap as create_sales_return — this
        # endpoint had *no* quantity validation at all before Sep 23, 2026,
        # not even the single-return check create had. Queried after the
        # delete+flush above so this return's own (already-deleted) old
        # items don't count against themselves.
        bill_items_by_batch: dict[str, BillItem] = {}
        already_returned_by_batch: dict[str, int] = {}
        if original_bill:
            bill_items_result = await db.execute(select(BillItem).where(BillItem.bill_id == original_bill.id))
            bill_items_by_batch = {bi.batch_number: bi for bi in bill_items_result.scalars().all()}

            prior_returns_result = await db.execute(
                select(SalesReturnItemORM.batch_number, SalesReturnItemORM.quantity)
                .join(SalesReturnORM, SalesReturnItemORM.sales_return_id == SalesReturnORM.id)
                .where(SalesReturnORM.original_bill_id == original_bill.id)
            )
            for batch_number, qty in prior_returns_result.all():
                already_returned_by_batch[batch_number] = already_returned_by_batch.get(batch_number, 0) + qty

        # Rebuild items
        total_paise = 0
        gst_paise = 0
        new_items: list[SalesReturnItemORM] = []

        # The real edit UI (SalesReturnEditModal) never sends product_sku/
        # medicine_id, only medicine_name/batch_no — without a fallback,
        # every edited item silently dropped (product stayed None ->
        # `continue`), zeroing the whole return. Found while adding
        # due-balance credit reversal here. Resolves via this return's own
        # pre-edit items (always available, bill or manual) rather than the
        # original bill's items, so it works for a manual return too.
        old_items_by_batch = {oi.batch_number: oi for oi in old_items}

        for item_data in update_data.items:
            orig_item = bill_items_by_batch.get(item_data.batch_no)
            if orig_item:
                already_returned = already_returned_by_batch.get(item_data.batch_no, 0)
                max_returnable = orig_item.quantity - already_returned
                if item_data.qty > max_returnable:
                    raise HTTPException(
                        status_code=400,
                        detail=(f"Return quantity for {item_data.medicine_name} ({item_data.qty}) exceeds "
                                f"the remaining returnable quantity ({max_returnable}) — "
                                f"{already_returned} of {orig_item.quantity} already returned."),
                    )

            sale_price_paise = int(item_data.mrp * 100)
            base_paise = sale_price_paise * item_data.qty
            disc_paise = int(base_paise * item_data.disc_percent / 100)
            after_disc_paise = base_paise - disc_paise
            line_gst_paise = int(after_disc_paise * item_data.gst_percent / 100)
            line_total_paise = after_disc_paise + line_gst_paise

            # Resolve product
            product: ProductORM | None = None
            if item_data.product_sku:
                prod_result = await db.execute(
                    select(ProductORM).where(
                        ProductORM.pharmacy_id == pharmacy_id,
                        ProductORM.sku == item_data.product_sku)
                )
                product = prod_result.scalar_one_or_none()
            if not product and item_data.medicine_id:
                try:
                    prod_result = await db.execute(select(ProductORM).where(
                        ProductORM.id == uuid.UUID(item_data.medicine_id),
                        ProductORM.pharmacy_id == pharmacy_id))
                    product = prod_result.scalar_one_or_none()
                except ValueError:
                    pass
            if not product:
                oi = old_items_by_batch.get(item_data.batch_no)
                if oi:
                    prod_result = await db.execute(select(ProductORM).where(
                        ProductORM.id == oi.product_id, ProductORM.pharmacy_id == pharmacy_id))
                    product = prod_result.scalar_one_or_none()
            if not product:
                continue

            # Same non-returnable block as create_sales_return above —
            # a same-day edit to an existing return can't add a
            # non-returnable item either.
            if not product.is_returnable:
                raise HTTPException(
                    status_code=400,
                    detail=f"{product.name} is marked as non-returnable and cannot be included in a sales return.")

            batch = await _find_batch(pharmacy_id, product.id, item_data.batch_id, item_data.batch_no, db)
            if not batch:
                continue

            # Only a bill-based return needs a bill_item FK — a manual
            # return (sales_return.original_bill_id is None) has none to link.
            bill_item_id: uuid.UUID | None = None
            if sales_return.original_bill_id:
                bill_item = await _find_bill_item(sales_return.original_bill_id, product.id, batch.id, db)
                if not bill_item:
                    bi_result = await db.execute(
                        select(BillItem).where(
                            BillItem.bill_id == sales_return.original_bill_id,
                            BillItem.batch_number == item_data.batch_no)
                    )
                    bill_item = bi_result.scalar_one_or_none()
                if not bill_item:
                    continue
                bill_item_id = bill_item.id

            return_to_stock = not item_data.is_damaged

            item_orm = SalesReturnItemORM(
                sales_return_id=rid,
                bill_item_id=bill_item_id,
                product_id=product.id,
                batch_id=batch.id,
                product_name=item_data.medicine_name,
                batch_number=item_data.batch_no,
                quantity=item_data.qty,
                sale_price_paise=sale_price_paise,
                gst_rate=item_data.gst_percent,
                gst_paise=line_gst_paise,
                line_total_paise=line_total_paise,
                return_to_stock=return_to_stock,
            )
            db.add(item_orm)
            new_items.append(item_orm)
            total_paise += after_disc_paise
            gst_paise += line_gst_paise

            reason = "Sales return (edit)" + (" (damaged)" if not return_to_stock else "")
            await _restore_stock(batch, item_data.qty, product, return_to_stock, pharmacy_id, user_id, rid, reason, db)

        grand_total_paise = round((total_paise + gst_paise) / 100) * 100
        requested_method = update_data.refund_method or sales_return.refund_method or "same_as_original"
        resolved_refund_method, new_credit_applied = _resolve_refund_and_credit(
            requested_method, grand_total_paise, original_bill)

        old_balance = old_paid = 0.0
        old_status = None
        if original_bill:
            old_balance = original_bill.balance_paise / 100
            old_paid = original_bill.amount_paid_paise / 100
            old_status = original_bill.status
        if new_credit_applied > 0:
            original_bill.amount_paid_paise += new_credit_applied
            original_bill.balance_paise = max(
                0, original_bill.grand_total_paise - original_bill.amount_paid_paise)
            if original_bill.balance_paise <= 0:
                original_bill.status = "paid"

        sales_return.total_paise = total_paise
        sales_return.total_gst_paise = gst_paise
        sales_return.grand_total_paise = grand_total_paise
        sales_return.refund_method = resolved_refund_method
        sales_return.credit_applied_paise = new_credit_applied

        await _record_audit(
            pharmacy_id, user_id, "financial_edit", "sales_return", rid,
            {"net_amount": grand_total_paise / 100, "refund_method": resolved_refund_method,
             "credit_applied": new_credit_applied / 100},
            db, ip_address=ip,
        )
        if old_credit_applied > 0 or new_credit_applied > 0:
            await _record_audit(
                pharmacy_id, user_id, "return_credit_adjusted", "invoice", original_bill.id,
                {"paid_amount": original_bill.amount_paid_paise / 100,
                 "due_amount": original_bill.balance_paise / 100, "status": original_bill.status},
                db,
                old_values={"paid_amount": old_paid, "due_amount": old_balance, "status": old_status},
                ip_address=ip,
            )

        await db.flush()
        await db.refresh(sales_return)  # updated_at has onupdate=func.now() — see purchases.py

        return _return_response(sales_return, new_items, original_bill)

    # Non-financial edit
    old_note = sales_return.notes
    old_refund_method = sales_return.refund_method
    if update_data.note is not None:
        sales_return.notes = update_data.note
        sales_return.return_reason = update_data.note
    if update_data.refund_method is not None:
        sales_return.refund_method = update_data.refund_method

    await _record_audit(
        pharmacy_id, user_id, "update", "sales_return", rid,
        {"note": sales_return.notes, "refund_method": sales_return.refund_method},
        db, old_values={"note": old_note, "refund_method": old_refund_method}, ip_address=ip,
    )

    await db.flush()
    await db.refresh(sales_return)  # updated_at has onupdate=func.now() — see purchases.py

    items_result = await db.execute(
        select(SalesReturnItemORM).where(SalesReturnItemORM.sales_return_id == rid)
    )
    # tenant-safe: sales_return already scoped
    bill_result = await db.execute(select(Bill).where(Bill.id == sales_return.original_bill_id))
    return _return_response(sales_return, items_result.scalars().all(),
                            bill_result.scalar_one_or_none())


# ── Role return permissions ────────────────────────────────────────────────────

@router.get("/roles/{role_name}/permissions/returns")
async def get_role_return_permissions(role_name: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    role = await find_role(db, pharmacy_id, role_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    perms = role.permissions if isinstance(role.permissions, list) else []
    return {
        "allow_financial_edit_return": "allow_financial_edit_return" in perms,
    }


@router.put("/roles/{role_id}/permissions/returns")
async def update_role_return_permissions(
    role_id: str,
    request: Request,
    allow_financial_edit_return: bool = False,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    await require_admin_or_super(current_user, db, detail="Only admins can update permissions")

    role = await get_role_or_404(db, role_id, uuid.UUID(current_user.pharmacy_id))

    old_perms = list(role.permissions) if isinstance(role.permissions, list) else []
    perms = list(old_perms)
    for perm, enabled in [("allow_financial_edit_return", allow_financial_edit_return)]:
        if enabled and perm not in perms:
            perms.append(perm)
        elif not enabled and perm in perms:
            perms.remove(perm)
    role.permissions = perms
    await db.flush()

    if perms != old_perms:
        await _record_audit(
            uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "update",
            "role", role.id, {"permissions": perms}, db,
            old_values={"permissions": old_perms}, ip_address=_client_ip(request) if request else None,
        )
        await db.flush()

    return {"message": "Permissions updated successfully"}


# ── Purchase analytics ────────────────────────────────────────────────────────

@router.get("/analytics/purchases")
async def get_purchase_analytics(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    # Purchases
    pur_query = select(
        func.count(PurchaseORM.id),
        func.coalesce(func.sum(PurchaseORM.grand_total_paise), 0),
    ).where(
        PurchaseORM.pharmacy_id == pharmacy_id,
        PurchaseORM.status.notin_(["cancelled", "draft"]),
    )
    if from_date:
        pur_query = pur_query.where(PurchaseORM.purchase_date >= date.fromisoformat(from_date[:10]))
    if to_date:
        pur_query = pur_query.where(PurchaseORM.purchase_date <= date.fromisoformat(to_date[:10]))
    pur_result = await db.execute(pur_query)
    pur_row = pur_result.one()
    total_purchases_count = pur_row[0]
    total_purchases_paise = pur_row[1]

    # Purchase returns
    ret_query = select(
        func.count(PurchaseReturnORM.id),
        func.coalesce(func.sum(PurchaseReturnORM.grand_total_paise), 0),
    ).where(
        PurchaseReturnORM.pharmacy_id == pharmacy_id,
        PurchaseReturnORM.status == "confirmed",
    )
    if from_date:
        ret_query = ret_query.where(PurchaseReturnORM.return_date >=
                                    date.fromisoformat(from_date[:10]))
    if to_date:
        ret_query = ret_query.where(PurchaseReturnORM.return_date <=
                                    date.fromisoformat(to_date[:10]))
    ret_result = await db.execute(ret_query)
    ret_row = ret_result.one()
    total_returns_count = ret_row[0]
    total_returns_paise = ret_row[1]

    total_purchases_value = total_purchases_paise / 100
    total_purchase_returns_value = total_returns_paise / 100

    return {
        "total_purchases_value": total_purchases_value,
        "total_purchase_returns_value": total_purchase_returns_value,
        "net_purchases": total_purchases_value - total_purchase_returns_value,
        "total_purchases_count": total_purchases_count,
        "total_returns_count": total_returns_count,
    }
