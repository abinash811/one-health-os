from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import (
    CATEGORY_HSN_MAP, DOSAGE_FORMS, PRODUCT_CATEGORIES,
    VALID_CATEGORIES, VALID_DOSAGE_FORMS, VALID_GST_RATES,
)
from deps import DbSession
from models.billing import Bill, BillItem, SalesReturn, SalesReturnItem
from models.pharmacy import PharmacySettings
from models.products import Product as ProductORM, StockBatch as BatchORM
from models.purchases import Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from models.suppliers import Supplier as SupplierORM
from models.users import AuditLog
from routers.auth_helpers import (
    User, get_current_user, get_owned_or_404, has_permission, paginate_response, resolve_store_override,
)

router = APIRouter(prefix="/api", tags=["inventory"])


# ── Pydantic request models ──────────────────────────────────────────────────

def _validate_category(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in VALID_CATEGORIES:
        raise ValueError(f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
    return v


def _validate_gst(v: Optional[float]) -> Optional[float]:
    if v is not None and v not in VALID_GST_RATES:
        allowed = ', '.join(str(r) for r in sorted(VALID_GST_RATES))
        raise ValueError(f"GST% must be one of: {allowed}")
    return v


def _validate_dosage_form(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in VALID_DOSAGE_FORMS:
        raise ValueError(f"Dosage form must be one of: {', '.join(sorted(VALID_DOSAGE_FORMS))}")
    return v


class ProductCreate(BaseModel):
    # SKU is optional — auto-generated server-side if not given. A pharmacist
    # shouldn't have to invent a unique code.
    sku: Optional[str] = None
    name: str
    manufacturer: Optional[str] = None
    brand: Optional[str] = None
    generic_name: Optional[str] = None
    dosage_form: Optional[str] = None
    pack_size: Optional[str] = None
    units_per_pack: int = 1
    category: Optional[str] = None
    barcode: Optional[str] = None
    gst_percent: float = 5.0
    schedule: Optional[str] = "OTC"
    low_stock_threshold_units: Optional[int] = 10
    reorder_quantity_units: Optional[int] = 100
    strength: Optional[str] = None
    requires_refrigeration: bool = False
    storage_location: Optional[str] = None
    is_returnable: bool = True

    _v_category = field_validator("category")(_validate_category)
    _v_gst = field_validator("gst_percent")(_validate_gst)
    _v_dosage = field_validator("dosage_form")(_validate_dosage_form)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    brand: Optional[str] = None
    generic_name: Optional[str] = None
    dosage_form: Optional[str] = None
    pack_size: Optional[str] = None
    units_per_pack: Optional[int] = None
    category: Optional[str] = None
    barcode: Optional[str] = None
    gst_percent: Optional[float] = None
    schedule: Optional[str] = None
    low_stock_threshold_units: Optional[int] = None
    reorder_quantity_units: Optional[int] = None
    strength: Optional[str] = None
    requires_refrigeration: Optional[bool] = None
    storage_location: Optional[str] = None
    is_returnable: Optional[bool] = None

    _v_category = field_validator("category")(_validate_category)
    _v_gst = field_validator("gst_percent")(_validate_gst)
    _v_dosage = field_validator("dosage_form")(_validate_dosage_form)


# ── helpers ───────────────────────────────────────────────────────────────────
# category/gst_percent/dosage_form validation errors reach the client via
# FastAPI's own automatic Pydantic validation (data: ProductCreate below) —
# its [{loc, msg}] shape is already handled by the shared axios interceptor
# (frontend/src/lib/axios.js), "Value error, " prefix and all.

async def _require_inventory_permission(current_user: User, action: str, db: AsyncSession) -> None:
    """Same pattern as purchases.py's _require_purchases_permission — creating
    or editing a product had no permission check at all until now, meaning
    any logged-in role (including cashier) could add/edit medicines."""
    if not await has_permission(current_user, f"inventory:{action}", db):
        raise HTTPException(
            status_code=403,
            detail=f"Your role does not have permission to {action} products")


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    old_values: dict | None = None, ip_address: str | None = None,
) -> None:
    """Same shared shape as suppliers.py/customers.py/purchases.py's own
    per-router copy — a medicine create/edit/delete previously left no
    record of who did it at all (docs/15_ROADMAP.md KNOWN ISSUES, found by
    scripts/check_audit_log_coverage.py)."""
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, new_values=new_values,
        old_values=old_values, ip_address=ip_address,
    ))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _product_response(p: ProductORM) -> dict:
    return {
        "id": str(p.id), "sku": p.sku, "name": p.name, "barcode": p.barcode,
        "manufacturer": p.manufacturer, "brand": p.brand, "pack_size": p.pack_size,
        "units_per_pack": p.units_per_pack, "category": p.category,
        "gst_percent": float(p.gst_rate), "discount_percent": float(p.discount_percent),
        "hsn_code": p.hsn_code,
        "schedule": p.drug_schedule, "generic_name": p.generic_name,
        "dosage_form": p.dosage_form, "strength": p.strength,
        "requires_refrigeration": p.requires_refrigeration,
        "is_returnable": p.is_returnable,
        "storage_location": p.storage_location,
        "low_stock_threshold_units": p.reorder_level,
        "reorder_quantity_units": p.reorder_quantity,
        "status": "active" if p.is_active else "inactive",
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _batch_for_billing(b: BatchORM, units_per_pack: int = 1) -> dict:
    # mrp_paise is already stored as a per-UNIT price (confirmed by batches.py's
    # own batch response, which returns mrp_paise/100 with no conversion) —
    # units_per_pack never applies to price. Found Sep 11, 2026 via a
    # live billing walkthrough: a ₹2.50/tablet, 10-tablet-strip medicine was
    # being sold for ₹0.25 — the extra "/ units_per_pack" here divided an
    # already-per-unit price a second time. Confirmed live in a real bill and
    # root-caused before fixing (see docs/15_ROADMAP.md RULE MISSES LOG).
    # quantity_on_hand is stored in real units, not packs, as of migration
    # a343c922f896 — total_units is just an alias, no multiplication needed.
    return {
        "batch_id": str(b.id), "batch_no": b.batch_number,
        "expiry_date": b.expiry_date.strftime("%d-%m-%Y") if b.expiry_date else "N/A",
        "expiry_iso": b.expiry_date.isoformat() if b.expiry_date else None,
        "qty_on_hand": b.quantity_on_hand, "total_units": b.quantity_on_hand,
        "mrp": b.mrp_paise / 100, "mrp_per_unit": b.mrp_paise / 100,
        "cost_price": b.cost_price_paise / 100,
    }


# ── /products CRUD ────────────────────────────────────────────────────────────

@router.post("/products")
async def create_product(data: ProductCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await _require_inventory_permission(current_user, "create", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    sku = data.sku or f"SKU-{uuid.uuid4().hex[:8].upper()}"
    existing = await db.execute(
        select(ProductORM).where(ProductORM.pharmacy_id == pharmacy_id, ProductORM.sku == sku)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")

    # HSN is derived from Category, never taken as free input — a retail
    # pharmacy only needs the four codes in CATEGORY_HSN_MAP, and letting it
    # be typed per product is how the same kind of item ends up miscoded
    # differently depending on who added it.
    # "medicine"/"surgical" use the pharmacy's own configured HSN codes
    # (Settings → Tax & GST) when set — found Sep 13, 2026 (Settings
    # product-review): those two fields saved but were never read anywhere,
    # always falling back to the fixed constant regardless of what a
    # pharmacy configured. The other two categories (first_aid, device)
    # have no equivalent Settings field, so they keep the fixed constant.
    ps_result = await db.execute(
        select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = ps_result.scalar_one_or_none()
    category_hsn_overrides = {
        "medicine": ps.default_hsn_medicines if ps else None,
        "surgical": ps.default_hsn_surgical if ps else None,
    }
    hsn_code = category_hsn_overrides.get(data.category) or CATEGORY_HSN_MAP.get(data.category, "3004")

    product = ProductORM(
        pharmacy_id=pharmacy_id, sku=sku, name=data.name,
        manufacturer=data.manufacturer, brand=data.brand, generic_name=data.generic_name,
        dosage_form=data.dosage_form, pack_size=data.pack_size,
        units_per_pack=data.units_per_pack, category=data.category, barcode=data.barcode,
        gst_rate=data.gst_percent, hsn_code=hsn_code,
        drug_schedule=data.schedule or "OTC", reorder_level=data.low_stock_threshold_units or 10,
        reorder_quantity=data.reorder_quantity_units or 100,
        strength=data.strength, requires_refrigeration=data.requires_refrigeration,
        storage_location=data.storage_location, is_returnable=data.is_returnable,
    )
    db.add(product)
    await db.flush()

    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "product", product.id,
        {"name": product.name, "sku": product.sku, "category": product.category,
         "gst_percent": float(product.gst_rate)},
        db, ip_address=_client_ip(request),
    )
    await db.flush()
    return _product_response(product)


@router.get("/products")
async def get_products(
    search: Optional[str] = None, category: Optional[str] = None,
    fields: Optional[str] = None, page: int = 1, page_size: int = 100, pharmacy_id: Optional[str] = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    # pharmacy_id here is the HQ-buyer store picker's optional override
    # (docs/26_MULTI_CHAIN_SCOPE.md Section 3 #3) — resolved and grant-
    # checked by resolve_store_override, never trusted as-is.
    pharmacy_id = await resolve_store_override(current_user, pharmacy_id, db)
    query = select(ProductORM).where(
        ProductORM.pharmacy_id == pharmacy_id,
        ProductORM.deleted_at.is_(None))
    if search:
        p = f"%{search}%"
        # Matches what InventorySearchBar.jsx's own placeholder already
        # promises ("Search medicine by name, generic, strength…") — generic
        # and strength were never actually searched until now.
        query = query.where(or_(
            ProductORM.name.ilike(p), ProductORM.sku.ilike(p),
            ProductORM.brand.ilike(p), ProductORM.manufacturer.ilike(p),
            ProductORM.generic_name.ilike(p), ProductORM.strength.ilike(p)))
    if category:
        query = query.where(ProductORM.category == category)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()
    result = await db.execute(query.order_by(ProductORM.name).offset((page - 1) * page_size).limit(page_size))
    products = [_product_response(p) for p in result.scalars().all()]
    if page > 1 or page_size != 100:
        return paginate_response(products, page, page_size, total)
    return products


# Static /products/* routes MUST be registered before /products/{product_id}

@router.get("/products/meta")
async def get_product_meta(current_user: User = Depends(get_current_user)):
    """Categories (with their fixed HSN + what's covered), GST slabs, and
    dosage forms — the Add Medicine form's dropdowns, from one source of
    truth instead of being duplicated in frontend constants."""
    return {
        "categories": PRODUCT_CATEGORIES,
        "gst_rates": sorted(VALID_GST_RATES),
        "dosage_forms": DOSAGE_FORMS,
    }


@router.post("/products/bulk-update")
async def bulk_update_products(data: dict, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # audit-exempt: found Sep 16, 2026 (scripts/check_audit_log_coverage.py) — real
    # gap, logged in docs/15_ROADMAP.md KNOWN ISSUES, not fixed in this pass
    await _require_inventory_permission(current_user, "edit", db)
    skus, field, value = data.get("skus", []), data.get("field", ""), data.get("value", "")
    if not skus or not field:
        raise HTTPException(status_code=400, detail="SKUs and field are required")
    field_map = {
        "gst_percent": "gst_rate",
        "schedule": "drug_schedule",
        "location": "storage_location"}
    col = field_map.get(field, field)
    allowed = {
        "storage_location", "gst_rate", "category", "drug_schedule", "brand",
        "discount_percent", "requires_refrigeration"}
    if col not in allowed:
        raise HTTPException(status_code=400, detail=f"Field '{field}' not allowed for bulk update")
    result = await db.execute(select(ProductORM).where(
        ProductORM.pharmacy_id == uuid.UUID(current_user.pharmacy_id), ProductORM.sku.in_(skus)))
    count = 0
    for product in result.scalars().all():
        if col in ("gst_rate", "discount_percent"):
            typed_value = float(value)
        elif col == "requires_refrigeration":
            typed_value = value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes")
        else:
            typed_value = value
        setattr(product, col, typed_value)
        count += 1
    await db.flush()
    return {"message": f"Updated {count} products", "modified_count": count}


@router.get("/products/search-with-batches")
async def search_products_with_batches(q: str,
                                       current_user: User = Depends(get_current_user),
                                       db: AsyncSession = DbSession):
    if len(q) < 2:
        return []
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    p = f"%{q}%"
    stmt = (
        select(ProductORM)
        .where(
            ProductORM.pharmacy_id == pharmacy_id,
            ProductORM.deleted_at.is_(None),
            or_(ProductORM.name.ilike(p), ProductORM.sku.ilike(p),
                ProductORM.brand.ilike(p), ProductORM.barcode == q),
        )
        .limit(50)
    )
    prod_result = await db.execute(stmt)
    results = []
    for product in prod_result.scalars().all():
        # Out-of-stock products used to be silently dropped here (`if not
        # batches: continue`) — a medicine that sold out simply vanished from
        # billing search with no explanation, which is exactly the "why did
        # it disappear" bug report this endpoint used to cause. It now
        # returns every match with has_stock (same field name the barcode
        # lookup above already uses) so the frontend can show it, clearly
        # marked unavailable, instead of hiding it.
        batches = await _get_active_batches(product, db)
        total_qty = sum(b["qty_on_hand"] for b in batches)
        results.append({
            "product_id": str(product.id), "sku": product.sku, "name": product.name,
            "brand": product.brand or "", "manufacturer": product.manufacturer or "",
            "composition": product.generic_name or "", "pack_size": product.pack_size or "",
            "units_per_pack": product.units_per_pack, "default_mrp": 0,
            "gst_percent": float(product.gst_rate), "schedule": product.drug_schedule,
            "scheduleH": product.drug_schedule in ["H", "H1"],
            "total_qty": total_qty, "total_units": total_qty,
            "has_stock": bool(batches),
            "batches": batches, "suggested_batch": batches[0] if batches else None,
        })
    # In-stock matches first — otherwise a name with many sold-out fixture/
    # historical products could bury the ones a cashier can actually sell.
    results.sort(key=lambda r: not r["has_stock"])
    return results


# Parameterized routes AFTER all static /products/* routes

@router.get("/products/{product_id}")
async def get_product(product_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # get_owned_or_404 already turns a malformed (non-UUID) id into a clean
    # 404 rather than an unhandled crash — same behavior as the old
    # try/except here, plus the pharmacy_id scoping that was missing.
    product = await get_owned_or_404(
        db, ProductORM, product_id, uuid.UUID(current_user.pharmacy_id),
        not_found_detail="Product not found")
    return _product_response(product)


@router.put("/products/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    # Was a hardcoded `role != "admin"` check — a magic-string role comparison
    # that bypassed the real permissions catalog entirely and blocked manager/
    # inventory_staff, who are granted "inventory:edit" per constants.py and
    # the Team > Roles UI, from ever editing a product. Found Sep 12, 2026
    # while wiring ACL into Suppliers/Products creation.
    await _require_inventory_permission(current_user, "edit", db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    product = await get_owned_or_404(
        db, ProductORM, product_id, pharmacy_id,
        not_found_detail="Product not found")
    field_map = {
        "gst_percent": "gst_rate",
        "schedule": "drug_schedule",
        "low_stock_threshold_units": "reorder_level",
        "reorder_quantity_units": "reorder_quantity"}
    updates = data.model_dump(exclude_unset=True)
    old_values: dict = {}
    new_values: dict = {}
    for key, value in updates.items():
        col = field_map.get(key, key)
        if hasattr(product, col):
            old_value = getattr(product, col)
            # gst_rate/discount_percent are Numeric columns — SQLAlchemy
            # returns a real Decimal at runtime regardless of the model's
            # `Mapped[float]` type hint, and Decimal isn't JSON-serializable
            # for the JSONB old_values/new_values columns below (confirmed
            # live: a real gst_percent edit 500'd until this was added).
            if isinstance(old_value, Decimal):
                old_value = float(old_value)
            if old_value != value:
                old_values[col] = old_value
                new_values[col] = value
            setattr(product, col, value)
    if "category" in updates:
        # Same pharmacy-configured HSN override as create_product — see
        # that function's comment.
        ps_result = await db.execute(
            select(PharmacySettings).where(PharmacySettings.pharmacy_id == product.pharmacy_id))
        ps = ps_result.scalar_one_or_none()
        category_hsn_overrides = {
            "medicine": ps.default_hsn_medicines if ps else None,
            "surgical": ps.default_hsn_surgical if ps else None,
        }
        product.hsn_code = (
            category_hsn_overrides.get(updates["category"])
            or CATEGORY_HSN_MAP.get(updates["category"], "3004")
        )

    if new_values:
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "update", "product", product.id,
            new_values, db, old_values=old_values, ip_address=_client_ip(request),
        )

    await db.flush()
    return {"message": "Product updated successfully"}


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    await _require_inventory_permission(current_user, "delete", db)
    product = await get_owned_or_404(
        db, ProductORM, product_id, pharmacy_id,
        not_found_detail="Product not found")
    pid = product.id
    batch_count = await db.execute(select(func.count()).select_from(BatchORM).where(
        BatchORM.product_id == pid, BatchORM.quantity_on_hand > 0))
    if batch_count.scalar() > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete product with stock. Write off batches first.")
    product.deleted_at = datetime.now(timezone.utc)
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "delete", "product", pid,
        {"deleted": True}, db,
        old_values={"name": product.name, "sku": product.sku}, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Product deleted successfully"}


async def _get_active_batches(product: ProductORM, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(BatchORM).where(
            BatchORM.product_id == product.id,
            BatchORM.is_active,
            BatchORM.quantity_on_hand > 0)
        .order_by(BatchORM.expiry_date)
    )
    return [_batch_for_billing(b, product.units_per_pack) for b in result.scalars().all()]


# ── /products transactions ────────────────────────────────────────────────────

@router.get("/products/{sku}/transactions")
async def get_product_transactions(
        sku: str,
        transaction_type: str = "all",
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    prod = await db.execute(select(ProductORM).where(
        ProductORM.pharmacy_id == uuid.UUID(current_user.pharmacy_id), ProductORM.sku == sku))
    product = prod.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    pid, out = product.id, {"product_sku": sku, "product_name": product.name,
                            "sales": [], "purchases": [], "sales_returns": [], "purchase_returns": []}
    if transaction_type in ["all", "sales"]:
        rows = await db.execute(
            select(BillItem, Bill.bill_number, Bill.bill_date, Bill.customer_name, Bill.status)
            .join(Bill, BillItem.bill_id == Bill.id).where(BillItem.product_id == pid)
            .order_by(Bill.bill_date.desc()).limit(200))
        for bi, bnum, bdate, cust, st in rows:
            out["sales"].append({"bill_number": bnum,
                                 "date": bdate.isoformat(),
                                 "customer_name": cust or "Walk-in",
                                 "batch_no": bi.batch_number,
                                 "quantity": bi.quantity,
                                 "unit_price": bi.sale_price_paise / 100,
                                 "discount": float(bi.discount_percent),
                                 "line_total": bi.line_total_paise / 100,
                                 "status": st})
    if transaction_type in ["all", "purchases"]:
        rows = await db.execute(
            select(PurchaseItem, Purchase.purchase_number, Purchase.purchase_date,
                   Purchase.supplier_invoice_number, Purchase.status, SupplierORM.name)
            .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
            .join(SupplierORM, Purchase.supplier_id == SupplierORM.id)
            .where(PurchaseItem.product_id == pid)
            .order_by(Purchase.purchase_date.desc()).limit(200))
        for pi, pnum, pdate, sup_inv, st, sup_name in rows:
            out["purchases"].append({"purchase_number": pnum,
                                     "date": pdate.isoformat(),
                                     "supplier_name": sup_name,
                                     "supplier_invoice": sup_inv,
                                     "batch_no": pi.batch_number or "–",
                                     "expiry_date": pi.expiry_date.isoformat() if pi.expiry_date else None,
                                     "quantity": pi.quantity_ordered,
                                     "cost_price": pi.cost_price_paise / 100,
                                     "mrp": pi.mrp_paise / 100,
                                     "line_total": pi.line_total_paise / 100,
                                     "status": st})
    if transaction_type in ["all", "sales_returns"]:
        rows = await db.execute(
            select(SalesReturnItem, SalesReturn.return_number, SalesReturn.return_date,
                   SalesReturn.status, Bill.bill_number, Bill.customer_name)
            .join(SalesReturn, SalesReturnItem.sales_return_id == SalesReturn.id)
            # Outer join: a manual return (no original_bill_id) must still show
            # up in a medicine's transaction history, not be silently dropped.
            .outerjoin(Bill, SalesReturn.original_bill_id == Bill.id)
            .where(SalesReturnItem.product_id == pid)
            .order_by(SalesReturn.return_date.desc()).limit(200))
        for sri, rnum, rdate, st, orig_bill_no, cust in rows:
            out["sales_returns"].append({"return_number": rnum,
                                         "date": rdate.isoformat(),
                                         "customer_name": cust or "Walk-in",
                                         "original_invoice": orig_bill_no,
                                         "batch_no": sri.batch_number,
                                         "quantity": sri.quantity,
                                         "refund_amount": sri.line_total_paise / 100,
                                         "status": st})
    if transaction_type in ["all", "purchase_returns"]:
        rows = await db.execute(
            select(PurchaseReturnItem, PurchaseReturn.return_number, PurchaseReturn.return_date,
                   PurchaseReturn.return_reason, PurchaseReturn.status,
                   Purchase.purchase_number, SupplierORM.name)
            .join(PurchaseReturn, PurchaseReturnItem.purchase_return_id == PurchaseReturn.id)
            .join(Purchase, PurchaseReturn.purchase_id == Purchase.id)
            .join(SupplierORM, PurchaseReturn.supplier_id == SupplierORM.id)
            .where(PurchaseReturnItem.product_id == pid)
            .order_by(PurchaseReturn.return_date.desc()).limit(200))
        for pri, rnum, rdate, reason, st, orig_purchase_no, sup_name in rows:
            out["purchase_returns"].append({"return_number": rnum,
                                            "date": rdate.isoformat(),
                                            "supplier_name": sup_name,
                                            "original_purchase": orig_purchase_no,
                                            "batch_no": pri.batch_number,
                                            "quantity": pri.quantity,
                                            "reason": reason,
                                            "line_total": pri.line_total_paise / 100,
                                            "status": st})
    return out


# ── /inventory health dashboard ───────────────────────────────────────────────

@router.get("/inventory")
async def get_inventory_with_health(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    brand_filter: Optional[str] = None,
    cold_chain_only: Optional[bool] = None,
    dosage_form_filter: Optional[str] = None,
    schedule_filter: Optional[str] = None,
    gst_filter: Optional[float] = None,
    location_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = DbSession,
):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    ps_result = await db.execute(select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = ps_result.scalar_one_or_none()
    near_expiry_days = ps.near_expiry_threshold_days if ps else 90

    query = select(ProductORM).where(
        ProductORM.pharmacy_id == pharmacy_id,
        ProductORM.deleted_at.is_(None))
    if search:
        p = f"%{search}%"
        query = query.where(or_(
            ProductORM.name.ilike(p), ProductORM.sku.ilike(p), ProductORM.brand.ilike(p),
            ProductORM.generic_name.ilike(p), ProductORM.strength.ilike(p)))
    if category_filter:
        query = query.where(ProductORM.category == category_filter)
    if brand_filter:
        query = query.where(ProductORM.brand == brand_filter)
    if cold_chain_only:
        query = query.where(ProductORM.requires_refrigeration.is_(True))
    if dosage_form_filter:
        query = query.where(ProductORM.dosage_form == dosage_form_filter)
    if schedule_filter:
        query = query.where(ProductORM.drug_schedule == schedule_filter)
    if gst_filter is not None:
        query = query.where(ProductORM.gst_rate == gst_filter)
    if location_filter:
        query = query.where(ProductORM.storage_location == location_filter)

    products = (await db.execute(query)).scalars().all()
    # No search/filters applied (the page's default landing state): show the
    # most recently added medicines first instead of the severity-based sort
    # below, so a pharmacy isn't greeted with the oldest-alphabetical items —
    # filters/search remain how a pharmacist reaches the rest of the catalog.
    no_filters_applied = not any([
        search, status_filter, category_filter, brand_filter, cold_chain_only,
        dosage_form_filter, schedule_filter, gst_filter is not None, location_filter])
    if no_filters_applied:
        products = sorted(products, key=lambda p: p.created_at, reverse=True)
    product_ids = [p.id for p in products]
    batch_rows = (await db.execute(select(BatchORM).where(
        BatchORM.product_id.in_(product_ids), BatchORM.is_active))).scalars().all()
    batches_by_pid: dict = {}
    for b in batch_rows:
        batches_by_pid.setdefault(b.product_id, []).append(b)

    today, near_threshold = date.today(), date.today() + timedelta(days=near_expiry_days)
    items = []
    for product in products:
        batches = batches_by_pid.get(product.id, [])
        total_qty = sum(b.quantity_on_hand for b in batches)
        active = [b for b in batches if b.quantity_on_hand > 0]
        nearest_expiry = min((b.expiry_date for b in active), default=None)
        has_expired = any(b.expiry_date < today for b in active)
        has_near = any(today <= b.expiry_date < near_threshold for b in active)
        if total_qty == 0:
            severity, status = 1, "out_of_stock"
        elif has_expired:
            severity, status = 1, "expired"
        elif has_near:
            severity, status = 2, "near_expiry"
        elif total_qty <= product.reorder_level:
            severity, status = 2, "low_stock"
        else:
            severity, status = 3, "healthy"
        items.append({"product": _product_response(product), "total_qty_units": total_qty,
                      "total_qty_packs": total_qty / max(product.units_per_pack, 1),
                      "nearest_expiry": nearest_expiry.isoformat() if nearest_expiry else None,
                      "severity": severity, "status": status, "batches_count": len(batches)})

    if status_filter == "low_stock":
        # Deliberately NOT `i["status"] == "low_stock"` — that status label
        # only applies when expiry hasn't already claimed the row (expiry
        # outranks low_stock there, for the single badge shown per row).
        # The filter itself uses the same plain stock<=reorder_level rule
        # as Dashboard and Reorder List, so a medicine that's both low-stock
        # and near-expiry/expired still shows up when a pharmacist asks for
        # "what's low on stock" — it still needs restocking either way.
        # Found Sep 19, 2026: Dashboard's Low Stock "View All" landed on an
        # empty-looking Inventory page for exactly this reason.
        items = [i for i in items if i["total_qty_units"] <= i["product"]["low_stock_threshold_units"]]
    elif status_filter:
        items = [i for i in items if i["status"] == status_filter]
    if not no_filters_applied:
        items.sort(
            key=lambda x: (
                x["severity"],
                x["nearest_expiry"] or "9999-12-31",
                x["product"]["name"].lower()))
    total_items = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "pagination": {"current_page": page, "page_size": page_size, "total_items": total_items,
                       "total_pages": (total_items + page_size - 1) // page_size,
                       "has_next": page * page_size < total_items, "has_prev": page > 1},
        "summary": {"critical_count": sum(1 for i in items if i["severity"] == 1),
                    "warning_count": sum(1 for i in items if i["severity"] == 2),
                    "healthy_count": sum(1 for i in items if i["severity"] == 3)},
    }


@router.get("/inventory/reorder-list")
async def get_reorder_list(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = DbSession,
):
    """The running "short book" / auto-reorder list — every product whose
    summed active-batch stock has fallen to or below its own reorder_level,
    regardless of expiry status (get_inventory_with_health's "low_stock"
    status deliberately excludes a product that's ALSO near-expiry/expired,
    since expiry outranks it there — but a product needing restock still
    needs restocking even if some of what's left is about to expire, so
    this list uses the bare stock<=reorder_level comparison directly).

    Reuses the exact same comparison as get_inventory_with_health
    (total_qty <= product.reorder_level) rather than a new definition —
    this codebase has already paid once for four disagreeing low-stock
    definitions drifting apart (see docs/15_ROADMAP.md RULE MISSES LOG,
    Aug 22, 2026), so any new "is this low stock" check reuses that one
    comparison, not a fifth.
    """
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    products = (await db.execute(select(ProductORM).where(
        ProductORM.pharmacy_id == pharmacy_id, ProductORM.deleted_at.is_(None)
    ))).scalars().all()
    product_ids = [p.id for p in products]
    batch_rows = (await db.execute(select(BatchORM).where(
        BatchORM.product_id.in_(product_ids), BatchORM.is_active))).scalars().all()
    batches_by_pid: dict = {}
    for b in batch_rows:
        batches_by_pid.setdefault(b.product_id, []).append(b)

    items = []
    for product in products:
        current_stock = sum(b.quantity_on_hand for b in batches_by_pid.get(product.id, []))
        if current_stock > product.reorder_level:
            continue
        items.append({
            "product": _product_response(product),
            "current_stock": current_stock,
            "reorder_level": product.reorder_level,
            "reorder_quantity": product.reorder_quantity,
            # How many units below the threshold right now — not a
            # suggested order quantity (that's reorder_quantity, the
            # pharmacist's own configured value); purely for sorting and
            # showing how urgent this row is.
            "shortfall": max(product.reorder_level - current_stock, 0),
        })

    items.sort(key=lambda i: (-i["shortfall"], i["product"]["name"].lower()))
    total_items = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "pagination": {"current_page": page, "page_size": page_size, "total_items": total_items,
                       "total_pages": (total_items + page_size - 1) // page_size,
                       "has_next": page * page_size < total_items, "has_prev": page > 1},
    }


@router.get("/inventory/filters")
async def get_inventory_filters(current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    base = ProductORM.pharmacy_id == pharmacy_id
    brands = await db.execute(select(ProductORM.brand).where(
        base, ProductORM.deleted_at.is_(None), ProductORM.brand.isnot(None)).distinct())
    locations = await db.execute(select(ProductORM.storage_location).where(
        base, ProductORM.deleted_at.is_(None), ProductORM.storage_location.isnot(None)).distinct())
    return {"brands": sorted([r[0] for r in brands if r[0]]),
            "locations": sorted([r[0] for r in locations if r[0]]),
            # Canonical lists, not distinct-from-data — category, dosage
            # form, and GST rate are constrained inputs (VALID_CATEGORIES/
            # VALID_DOSAGE_FORMS/VALID_GST_RATES in constants.py, the same
            # source Add Medicine's dropdowns use), not free text like
            # brand/location, so every valid choice should be offered even
            # before any product uses it. Was distinct-from-data until a
            # pharmacist with only "medicine"-category products found they
            # could never bulk-assign "surgical"/"first_aid"/"device" since
            # those never showed up (docs/15_ROADMAP.md RULE MISSES LOG).
            "categories": PRODUCT_CATEGORIES,
            "dosage_forms": DOSAGE_FORMS,
            "schedules": [
                {"value": "OTC", "label": "OTC — Over the Counter"},
                {"value": "H", "label": "H — Prescription Required"},
                {"value": "H1", "label": "H1 — Prescription + 3yr Register"},
                {"value": "X", "label": "X — Narcotic"},
            ],
            "gst_rates": sorted(VALID_GST_RATES),
            "statuses": [{"value": "out_of_stock",
                          "label": "Out of Stock"},
                         {"value": "expired",
                          "label": "Expired"},
                         {"value": "near_expiry",
                          "label": "Near Expiry"},
                         {"value": "low_stock",
                          "label": "Low Stock"},
                         {"value": "healthy",
                          "label": "Healthy"}],
            }
