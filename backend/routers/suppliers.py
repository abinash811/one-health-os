from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.pharmacy import PharmacySettings
from models.products import Product as ProductORM, StockBatch as BatchORM
from models.purchases import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn
from models.suppliers import Supplier as SupplierORM
from models.users import AuditLog
from routers.auth_helpers import (
    User, get_current_user, get_owned_or_404, has_permission, resolve_store_override,
    resolve_store_override_for_write,
)

router = APIRouter(prefix="/api", tags=["suppliers"])


async def _require_suppliers_permission(current_user: User, action: str, db: AsyncSession) -> None:
    """Same pattern as purchases.py's _require_purchases_permission — creating
    or editing a supplier had no permission check at all until now, meaning
    any logged-in role (including cashier) could create/edit distributors."""
    if not await has_permission(current_user, f"suppliers:{action}", db):
        raise HTTPException(
            status_code=403,
            detail=f"Your role does not have permission to {action} suppliers")


# ── Pydantic request models ──────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    payment_terms_days: int = 30
    credit_days: Optional[int] = None
    notes: Optional[str] = None
    # Optional — set only when an HQ-authorized person creates this
    # supplier while placing an order for a DIFFERENT store
    # (docs/26_MULTI_CHAIN_SCOPE.md Section 3 #3). Omitted/blank = today's
    # behavior, unchanged: the supplier belongs to the caller's own
    # currently active store.
    pharmacy_id: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    payment_terms_days: Optional[int] = None
    credit_days: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierPaymentRequest(BaseModel):
    amount: float
    payment_method: str = "cash"
    payment_date: Optional[str] = None
    note: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _supplier_response(
        s: SupplierORM, outstanding_paise: int = 0, payment_history: Optional[list] = None) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "contact_person": s.contact_person,
        "phone": s.phone,
        "email": s.email,
        "gstin": s.gstin,
        "address": s.address,
        "city": s.city,
        "state": s.state,
        "pincode": s.pincode,
        "drug_license_number": s.drug_license_number,
        "payment_terms_days": s.credit_days,
        "credit_days": s.credit_days,
        "notes": s.notes,
        "is_active": s.is_active,
        "outstanding": outstanding_paise / 100,
        "payment_history": payment_history if payment_history is not None else [],
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


async def _outstanding_paise_by_suppliers(
        supplier_ids: list[uuid.UUID], db: AsyncSession) -> dict[uuid.UUID, int]:
    """Batched version of _calc_outstanding for list pages — one grouped
    query instead of N+1 (same pattern as customers.py's
    _outstanding_paise_by_customer). get_suppliers() never called
    _calc_outstanding() at all before this, which is why the list page
    always showed outstanding as ₹0 regardless of real unpaid purchases
    (docs/15_ROADMAP.md Suppliers audit, Sep 12, 2026)."""
    if not supplier_ids:
        return {}

    gross_result = await db.execute(
        select(Purchase.supplier_id, func.sum(Purchase.grand_total_paise - Purchase.amount_paid_paise))
        .where(Purchase.supplier_id.in_(supplier_ids), Purchase.payment_status.in_(["unpaid", "partial"]))
        .group_by(Purchase.supplier_id)
    )
    gross_by_id = dict(gross_result.all())

    returns_result = await db.execute(
        select(PurchaseReturn.supplier_id, func.sum(PurchaseReturn.grand_total_paise))
        .where(PurchaseReturn.supplier_id.in_(supplier_ids), PurchaseReturn.status == "confirmed")
        .group_by(PurchaseReturn.supplier_id)
    )
    returns_by_id = dict(returns_result.all())

    return {sid: max(0, gross_by_id.get(sid, 0) - returns_by_id.get(sid, 0)) for sid in supplier_ids}


async def _payment_history_by_suppliers(
        supplier_ids: list[uuid.UUID], db: AsyncSession) -> dict[uuid.UUID, list[dict]]:
    """Merges real supplier payments (via the purchases they were applied
    to) and confirmed purchase returns (credit notes) into one
    chronological ledger per supplier — the payment_history shape
    SupplierDetailPanel's Outstanding tab already renders, which nothing
    in the backend ever populated until now."""
    if not supplier_ids:
        return {}

    history: dict[uuid.UUID, list[dict]] = {sid: [] for sid in supplier_ids}

    payments_result = await db.execute(
        select(PurchasePayment.id, Purchase.supplier_id, PurchasePayment.payment_date,
               PurchasePayment.amount_paise, PurchasePayment.notes)
        .join(Purchase, PurchasePayment.purchase_id == Purchase.id)
        .where(Purchase.supplier_id.in_(supplier_ids), PurchasePayment.reversed_at.is_(None))
    )
    for pid, sid, pay_date, amount_paise, notes in payments_result.all():
        history[sid].append({
            "id": str(pid), "date": pay_date.isoformat(), "type": "payment",
            "amount": amount_paise / 100, "note": notes,
        })

    returns_result = await db.execute(
        select(PurchaseReturn.id, PurchaseReturn.supplier_id, PurchaseReturn.return_date,
               PurchaseReturn.grand_total_paise, PurchaseReturn.return_number)
        .where(PurchaseReturn.supplier_id.in_(supplier_ids), PurchaseReturn.status == "confirmed")
    )
    for rid, sid, ret_date, grand_total_paise, return_number in returns_result.all():
        history[sid].append({
            "id": str(rid), "date": ret_date.isoformat(), "type": "purchase_return",
            "amount": grand_total_paise / 100, "note": f"Return {return_number}",
        })

    for entries in history.values():
        entries.sort(key=lambda h: h["date"])

    return history


# ── /suppliers ────────────────────────────────────────────────────────────────

@router.get("/suppliers")
async def get_suppliers(
    search: Optional[str] = None, active_only: Optional[bool] = None,
    page: int = 1, page_size: int = 50, pharmacy_id: Optional[str] = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    # pharmacy_id here is the HQ-buyer store picker's optional override
    # (docs/26_MULTI_CHAIN_SCOPE.md Section 3 #3) — resolved and grant-
    # checked by resolve_store_override, never trusted as-is.
    pharmacy_id = await resolve_store_override(current_user, pharmacy_id, db)

    query = select(SupplierORM).where(
        SupplierORM.pharmacy_id == pharmacy_id,
        SupplierORM.deleted_at.is_(None))
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(
            SupplierORM.name.ilike(pattern),
            SupplierORM.contact_person.ilike(pattern),
            SupplierORM.phone.ilike(pattern),
            SupplierORM.gstin.ilike(pattern),
        ))
    if active_only:
        query = query.where(SupplierORM.is_active)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(SupplierORM.name).offset(offset).limit(page_size))
    rows = result.scalars().all()

    ids = [s.id for s in rows]
    outstanding_by_id = await _outstanding_paise_by_suppliers(ids, db)
    history_by_id = await _payment_history_by_suppliers(ids, db)
    suppliers = [
        _supplier_response(s, outstanding_by_id.get(s.id, 0), history_by_id.get(s.id, []))
        for s in rows
    ]

    return {
        "data": suppliers,
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total, "has_prev": page > 1,
        },
    }


@router.post("/suppliers")
async def create_supplier(
        supplier_data: SupplierCreate, request: Request,
        current_user: User = Depends(get_current_user), db: AsyncSession = DbSession):
    pharmacy_id = await resolve_store_override_for_write(
        current_user, supplier_data.pharmacy_id, "suppliers:create", db)
    existing = await db.execute(
        select(SupplierORM).where(
            SupplierORM.pharmacy_id == pharmacy_id,
            SupplierORM.name == supplier_data.name,
            SupplierORM.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Supplier with this name already exists")

    supplier = SupplierORM(
        pharmacy_id=pharmacy_id,
        name=supplier_data.name,
        contact_person=supplier_data.contact_person,
        phone=supplier_data.phone,
        email=supplier_data.email,
        gstin=supplier_data.gstin,
        address=supplier_data.address,
        notes=supplier_data.notes,
        credit_days=(supplier_data.payment_terms_days
                     if supplier_data.credit_days is None else supplier_data.credit_days),
    )
    db.add(supplier)
    await db.flush()

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "supplier", supplier.id,
        {"name": supplier.name, "phone": supplier.phone, "gstin": supplier.gstin,
         "credit_days": supplier.credit_days},
        db, ip_address=_client_ip(request),
    )
    await db.flush()
    return _supplier_response(supplier)


@router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Supplier not found")

    outstanding = await _calc_outstanding(supplier.id, db)
    history_by_id = await _payment_history_by_suppliers([supplier.id], db)
    return _supplier_response(supplier, outstanding, history_by_id.get(supplier.id, []))


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
        supplier_id: str,
        supplier_data: SupplierUpdate,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    await _require_suppliers_permission(current_user, "edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, pharmacy_id,
        not_found_detail="Supplier not found")

    update_fields = supplier_data.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    field_map = {"payment_terms_days": "credit_days"}
    old_values: dict = {}
    new_values: dict = {}
    for key, value in update_fields.items():
        col = field_map.get(key, key)
        if hasattr(supplier, col):
            old_value = getattr(supplier, col)
            if old_value != value:
                old_values[col] = old_value
                new_values[col] = value
            setattr(supplier, col, value)

    if new_values:
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "update", "supplier", supplier.id,
            new_values, db, old_values=old_values, ip_address=_client_ip(request),
        )

    await db.flush()
    return {"message": "Supplier updated successfully"}


@router.post("/suppliers/{supplier_id}/payment")
async def record_supplier_payment(
        supplier_id: str,
        payment: SupplierPaymentRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    """Suppliers never had a way to record a payment — the frontend's
    'Record Payment' button (SupplierPaymentModal) posted to this exact
    route and got a 404 every time (docs/15_ROADMAP.md Suppliers audit,
    Sep 12, 2026). Outstanding is computed from individual Purchase rows
    (_calc_outstanding), so a supplier-level payment is allocated FIFO —
    oldest unpaid/partial purchase first — writing to the same
    Purchase.amount_paid_paise/payment_status + PurchasePayment rows
    that purchases.py's own per-purchase mark_purchase_paid() writes to,
    so both stay consistent with each other."""
    await _require_suppliers_permission(current_user, "edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    sid = uuid.UUID(supplier_id)

    supplier = await get_owned_or_404(
        db, SupplierORM, sid, pharmacy_id, not_found_detail="Supplier not found")

    payment_paise = int(round(payment.amount * 100))
    if payment_paise <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    outstanding_before = await _calc_outstanding(sid, db)
    if payment_paise > outstanding_before:
        raise HTTPException(
            status_code=400,
            detail=(f"Payment amount exceeds {supplier.name}'s outstanding balance "
                    f"of ₹{outstanding_before / 100:.2f}"),
        )

    payment_dt = date.fromisoformat(payment.payment_date[:10]) if payment.payment_date else date.today()

    open_purchases_result = await db.execute(
        select(Purchase)
        .where(Purchase.supplier_id == sid, Purchase.payment_status.in_(["unpaid", "partial"]))
        .order_by(Purchase.purchase_date, Purchase.created_at)
    )
    open_purchases = open_purchases_result.scalars().all()

    remaining_paise = payment_paise
    for purchase in open_purchases:
        if remaining_paise <= 0:
            break
        purchase_due = purchase.grand_total_paise - purchase.amount_paid_paise
        if purchase_due <= 0:
            continue
        applied = min(purchase_due, remaining_paise)

        purchase.amount_paid_paise += applied
        purchase.payment_status = "paid" if purchase.amount_paid_paise >= purchase.grand_total_paise else "partial"

        db.add(PurchasePayment(
            pharmacy_id=pharmacy_id,
            purchase_id=purchase.id,
            amount_paise=applied,
            payment_method=payment.payment_method,
            payment_date=payment_dt,
            notes=payment.note,
            created_by=uuid.UUID(current_user.id),
        ))
        remaining_paise -= applied

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "payment", "supplier", sid,
        {"amount": payment.amount, "payment_method": payment.payment_method,
         "payment_date": payment_dt.isoformat(), "note": payment.note},
        db,
        old_values={"outstanding": outstanding_before / 100},
        ip_address=_client_ip(request),
    )
    await db.flush()

    outstanding_after = await _calc_outstanding(sid, db)
    history_by_id = await _payment_history_by_suppliers([sid], db)
    return _supplier_response(supplier, outstanding_after, history_by_id.get(sid, []))


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_suppliers_permission(current_user, "deactivate", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, pharmacy_id, not_found_detail="Supplier not found")
    sid = supplier.id

    count_result = await db.execute(select(func.count()).select_from(Purchase).where(Purchase.supplier_id == sid))
    purchase_count = count_result.scalar()
    if purchase_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete supplier: {purchase_count} purchase(s) exist. Deactivate instead.",
        )

    supplier.deleted_at = datetime.now(timezone.utc)
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "delete", "supplier", sid,
        {"deleted": True}, db,
        old_values={"name": supplier.name, "phone": supplier.phone}, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Supplier deleted successfully"}


@router.patch("/suppliers/{supplier_id}/toggle-status")
async def toggle_supplier_status(supplier_id: str, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # toggle-status had zero permission check until now — same class of
    # gap as the ACL miss already fixed for create/edit/delete on this
    # router; found while wiring audit logging into every mutating
    # endpoint here. Reuses "deactivate", the same permission delete_supplier
    # requires, since both control whether a supplier stays usable.
    await _require_suppliers_permission(current_user, "deactivate", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, pharmacy_id,
        not_found_detail="Supplier not found")

    old_status = supplier.is_active
    supplier.is_active = not supplier.is_active
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update", "supplier", supplier.id,
        {"is_active": supplier.is_active}, db,
        old_values={"is_active": old_status}, ip_address=_client_ip(request),
    )
    await db.flush()
    status_text = "activated" if supplier.is_active else "deactivated"
    return {"message": f"Supplier {status_text} successfully", "is_active": supplier.is_active}


@router.get("/suppliers/{supplier_id}/summary")
async def get_supplier_summary(supplier_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Supplier not found")
    sid = supplier.id

    # Confirmed only — a draft is not a real purchase yet (no stock moved,
    # no money owed). Was `status.in_(["confirmed", "draft"])`, so a
    # supplier's total-purchases count/value on this one screen included
    # purchases that were never actually placed — found Sep 13, 2026,
    # Purchases follow-up.
    purchases_result = await db.execute(
        select(Purchase.grand_total_paise, Purchase.purchase_date)
        .where(Purchase.supplier_id == sid, Purchase.status == "confirmed")
    )
    purchases = purchases_result.all()

    total_purchases = len(purchases)
    total_value = sum(p.grand_total_paise for p in purchases) / 100
    last_purchase_date = max((p.purchase_date for p in purchases), default=None)

    outstanding = await _calc_outstanding(sid, db)

    return {
        "supplier": _supplier_response(supplier, outstanding),
        "total_purchases": total_purchases,
        "total_purchase_value": round(total_value, 2),
        "last_purchase_date": last_purchase_date.isoformat() if last_purchase_date else None,
    }


@router.get("/suppliers/{supplier_id}/near-expiry-batches")
async def get_supplier_near_expiry_batches(supplier_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    """Named Pharmasoft feature (return-to-supplier before expiry write-
    off) — PharmaCare's purchase-return flow was real but purely
    reactive; nothing proactively surfaced near-expiry stock bought from
    a given supplier as a return candidate before it becomes a loss.
    Joins StockBatch -> PurchaseItem (via batch_id) -> Purchase to find
    which supplier a batch was originally bought from, reusing the same
    near_expiry_threshold_days setting inventory.py's health dashboard
    already uses, so "near expiry" means the same thing everywhere."""
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    supplier = await get_owned_or_404(
        db, SupplierORM, supplier_id, pharmacy_id, not_found_detail="Supplier not found")
    sid = supplier.id

    ps_result = await db.execute(select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = ps_result.scalar_one_or_none()
    near_expiry_days = ps.near_expiry_threshold_days if ps else 90
    near_threshold = date.today() + timedelta(days=near_expiry_days)

    rows = await db.execute(
        select(BatchORM, PurchaseItem.purchase_id, ProductORM.name, ProductORM.sku)
        .join(PurchaseItem, PurchaseItem.batch_id == BatchORM.id)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(ProductORM, ProductORM.id == BatchORM.product_id)
        .where(
            Purchase.supplier_id == sid,
            Purchase.pharmacy_id == pharmacy_id,  # explicit, though sid is already pharmacy-scoped via get_owned_or_404
            BatchORM.is_active.is_(True),
            BatchORM.quantity_on_hand > 0,
            BatchORM.expiry_date < near_threshold,
        )
        .order_by(BatchORM.expiry_date)
    )

    today = date.today()
    items = [
        {
            "batch_id": str(batch.id),
            "purchase_id": str(purchase_id),
            "product_name": product_name,
            "product_sku": product_sku,
            "batch_number": batch.batch_number,
            "expiry_date": batch.expiry_date.isoformat(),
            "is_expired": batch.expiry_date < today,
            "quantity_on_hand": batch.quantity_on_hand,
            "value_at_risk": (batch.quantity_on_hand * batch.cost_price_paise) / 100,
        }
        for batch, purchase_id, product_name, product_sku in rows.all()
    ]

    return {"near_expiry_threshold_days": near_expiry_days, "items": items}


async def _calc_outstanding(supplier_id: uuid.UUID, db: AsyncSession) -> int:
    """Calculate outstanding paise = sum(grand_total - amount_paid) for
    unpaid/partial purchases, minus confirmed purchase returns.

    A confirmed PurchaseReturn issues a credit note but never touches the
    original Purchase row's grand_total_paise/amount_paid_paise/
    payment_status — so without this, a supplier's outstanding balance
    overstated what's actually owed once returns exist. Matches how a
    real supplier ledger works: a credit note reduces the account's
    overall balance, not necessarily the specific invoice it was against.
    """
    result = await db.execute(
        select(func.coalesce(func.sum(Purchase.grand_total_paise - Purchase.amount_paid_paise), 0))
        .where(Purchase.supplier_id == supplier_id, Purchase.payment_status.in_(["unpaid", "partial"]))
    )
    gross_outstanding = result.scalar()

    returns_result = await db.execute(
        select(func.coalesce(func.sum(PurchaseReturn.grand_total_paise), 0))
        .where(PurchaseReturn.supplier_id == supplier_id, PurchaseReturn.status == "confirmed")
    )
    returns_credit = returns_result.scalar()

    return max(0, gross_outstanding - returns_credit)
