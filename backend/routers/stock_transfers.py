"""
Cross-store stock transfer — multi-chain Phase 2, Step 5
(docs/26_MULTI_CHAIN_SCOPE.md). Moves real stock from one pharmacy in a
chain to another, instantly (v1 — no in-transit holding state), always
admin-only and audit-logged on BOTH the source and destination pharmacy's
own audit trail (direct instruction: audit logs must be present and
clear on this feature).

**Only allowed between two stores with the same GSTIN** (added Sep 27,
2026, direct instruction, after confirming the real legal risk: two
stores with different GSTINs are distinct "persons" under GST law, so
moving stock between them is a taxable "supply" requiring a proper tax
invoice, and typically a Wholesale Drug License to boot — not something
this app generates or verifies. Real competitor eVitalRx blocks this
exact case for the same reason. Rather than build the license/document
flow, the simple and safe choice is to not allow the transfer at all
unless both stores are confirmed to share one GSTIN.) A missing GSTIN on
either side is rejected too — "not proven different" is not the same as
"confirmed same." `is_cross_gstin`/`source_gstin`/`destination_gstin`
stay on the model for historical transfers made before this change; new
transfers can never set `is_cross_gstin=True` since the create endpoint
now blocks that case before it can happen.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from deps import DbSession
from models.pharmacy import Pharmacy as PharmacyORM
from models.products import Product as ProductORM, StockBatch as BatchORM, StockMovement as MovementORM
from models.stock_transfers import StockTransfer, StockTransferItem
from models.users import AuditLog
from routers.auth_helpers import User, get_current_user, require_admin_or_super

router = APIRouter(prefix="/api", tags=["stock-transfers"])


class StockTransferItemCreate(BaseModel):
    product_sku: str
    batch_number: str
    quantity: int


class StockTransferCreate(BaseModel):
    destination_pharmacy_id: str
    notes: Optional[str] = None
    items: List[StockTransferItemCreate]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_movement(
    pharmacy_id: uuid.UUID, product_id: uuid.UUID, batch_id: uuid.UUID,
    movement_type: str, quantity: int, qty_before: int, qty_after: int,
    reference_id: uuid.UUID, user_id: uuid.UUID, notes: str, db: AsyncSession,
) -> None:
    db.add(MovementORM(
        pharmacy_id=pharmacy_id, product_id=product_id, batch_id=batch_id,
        movement_type=movement_type, quantity=quantity,
        quantity_before=qty_before, quantity_after=qty_after,
        reference_type="stock_transfer", reference_id=reference_id,
        user_id=user_id, notes=notes,
    ))


async def _record_audit(
    pharmacy_id: uuid.UUID, user_id: uuid.UUID, action: str,
    entity_id: uuid.UUID, new_values: dict, db: AsyncSession,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, user_id=user_id, action=action,
        entity_type="stock_transfer", entity_id=entity_id, new_values=new_values,
        ip_address=ip_address,
    ))


async def _get_pharmacy(pharmacy_id: uuid.UUID, db: AsyncSession) -> PharmacyORM:
    result = await db.execute(select(PharmacyORM).where(PharmacyORM.id == pharmacy_id))
    pharmacy = result.scalar_one_or_none()
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return pharmacy


async def _get_or_create_destination_product(
    source_product: ProductORM, destination_pharmacy_id: uuid.UUID, db: AsyncSession,
) -> ProductORM:
    """Products are stored separately per store (unique SKU per pharmacy,
    not shared) — so the destination store may not have this medicine's
    product row yet. Auto-create it there, copying the catalog fields
    from source, rather than asking the pharmacist to set it up first."""
    existing = await db.execute(
        select(ProductORM).where(
            ProductORM.pharmacy_id == destination_pharmacy_id,
            ProductORM.sku == source_product.sku,
        )
    )
    product = existing.scalar_one_or_none()
    if product:
        return product
    product = ProductORM(
        pharmacy_id=destination_pharmacy_id, sku=source_product.sku,
        barcode=source_product.barcode, name=source_product.name,
        generic_name=source_product.generic_name, brand=source_product.brand,
        manufacturer=source_product.manufacturer, category=source_product.category,
        drug_schedule=source_product.drug_schedule, dosage_form=source_product.dosage_form,
        strength=source_product.strength, pack_size=source_product.pack_size,
        units_per_pack=source_product.units_per_pack, hsn_code=source_product.hsn_code,
        gst_rate=source_product.gst_rate, discount_percent=source_product.discount_percent,
        reorder_level=source_product.reorder_level, reorder_quantity=source_product.reorder_quantity,
        requires_refrigeration=source_product.requires_refrigeration,
        is_returnable=source_product.is_returnable,
    )
    db.add(product)
    await db.flush()
    return product


async def _get_or_create_destination_batch(
    destination_product_id: uuid.UUID, destination_pharmacy_id: uuid.UUID,
    source_batch: BatchORM, quantity: int, db: AsyncSession,
) -> BatchORM:
    existing = await db.execute(
        select(BatchORM).where(
            BatchORM.product_id == destination_product_id,
            BatchORM.batch_number == source_batch.batch_number,
            BatchORM.is_active.is_(True),
        )
    )
    batch = existing.scalar_one_or_none()
    if batch:
        return batch
    batch = BatchORM(
        pharmacy_id=destination_pharmacy_id, product_id=destination_product_id,
        batch_number=source_batch.batch_number, expiry_date=source_batch.expiry_date,
        manufacture_date=source_batch.manufacture_date,
        mrp_paise=source_batch.mrp_paise, cost_price_paise=source_batch.cost_price_paise,
        quantity_received=0, quantity_on_hand=0,
    )
    db.add(batch)
    await db.flush()
    return batch


@router.post("/stock-transfers")
async def create_stock_transfer(
    body: StockTransferCreate, request: Request,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    await require_admin_or_super(current_user, db)
    source_pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    destination_pharmacy_id = uuid.UUID(body.destination_pharmacy_id)

    if destination_pharmacy_id == source_pharmacy_id:
        raise HTTPException(status_code=400, detail="Source and destination store must be different")
    if not body.items:
        raise HTTPException(status_code=400, detail="Add at least one item to transfer.")

    source_pharmacy = await _get_pharmacy(source_pharmacy_id, db)
    destination_pharmacy = await _get_pharmacy(destination_pharmacy_id, db)
    if destination_pharmacy.chain_id != source_pharmacy.chain_id:
        raise HTTPException(status_code=403, detail="That store is not in your workspace")

    # Moving stock between two different GSTINs is a taxable "supply" under
    # GST law and typically needs a Wholesale Drug License — neither of
    # which this app verifies or generates. Block rather than risk it; a
    # missing GSTIN on either side can't be confirmed as "the same," so it's
    # rejected too, not silently allowed through.
    if not source_pharmacy.gstin or not destination_pharmacy.gstin:
        raise HTTPException(
            status_code=400,
            detail="Both stores must have their GSTIN set in Settings before stock can be "
                   "transferred between them.")
    if source_pharmacy.gstin != destination_pharmacy.gstin:
        raise HTTPException(
            status_code=403,
            detail="Stock transfer is only allowed between stores with the same GSTIN. "
                   "Stores with different GSTINs are separate tax entities — moving stock "
                   "between them is a taxable supply that needs its own tax invoice and "
                   "typically a Wholesale Drug License, which this app does not handle.")

    is_cross_gstin = False

    transfer_number = f"TRF-{date.today().year}-{uuid.uuid4().hex[:6].upper()}"
    transfer = StockTransfer(
        transfer_number=transfer_number,
        source_pharmacy_id=source_pharmacy_id, destination_pharmacy_id=destination_pharmacy_id,
        is_cross_gstin=is_cross_gstin, source_gstin=source_pharmacy.gstin,
        destination_gstin=destination_pharmacy.gstin, notes=body.notes,
        initiated_by=uuid.UUID(current_user.id),
    )
    db.add(transfer)
    await db.flush()

    transferred_items = []
    for item in body.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

        source_product_result = await db.execute(
            select(ProductORM).where(
                ProductORM.pharmacy_id == source_pharmacy_id, ProductORM.sku == item.product_sku))
        source_product = source_product_result.scalar_one_or_none()
        if not source_product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_sku} not found")

        source_batch_result = await db.execute(
            select(BatchORM).where(
                BatchORM.product_id == source_product.id, BatchORM.batch_number == item.batch_number,
                BatchORM.is_active.is_(True)))
        source_batch = source_batch_result.scalar_one_or_none()
        if not source_batch:
            raise HTTPException(status_code=404, detail=f"Batch {item.batch_number} not found")
        if item.quantity > source_batch.quantity_on_hand:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock in batch {item.batch_number} "
                       f"(have {source_batch.quantity_on_hand}, requested {item.quantity})")

        destination_product = await _get_or_create_destination_product(source_product, destination_pharmacy_id, db)
        destination_batch = await _get_or_create_destination_batch(
            destination_product.id, destination_pharmacy_id, source_batch, item.quantity, db)

        source_before = source_batch.quantity_on_hand
        source_batch.quantity_on_hand -= item.quantity
        destination_before = destination_batch.quantity_on_hand
        destination_batch.quantity_on_hand += item.quantity
        destination_batch.quantity_received += item.quantity

        await _record_movement(
            pharmacy_id=source_pharmacy_id, product_id=source_product.id, batch_id=source_batch.id,
            movement_type="transfer_out", quantity=-item.quantity,
            qty_before=source_before, qty_after=source_batch.quantity_on_hand,
            reference_id=transfer.id, user_id=uuid.UUID(current_user.id),
            notes=f"Transfer {transfer_number} to {destination_pharmacy.name}", db=db,
        )
        await _record_movement(
            pharmacy_id=destination_pharmacy_id, product_id=destination_product.id, batch_id=destination_batch.id,
            movement_type="transfer_in", quantity=item.quantity,
            qty_before=destination_before, qty_after=destination_batch.quantity_on_hand,
            reference_id=transfer.id, user_id=uuid.UUID(current_user.id),
            notes=f"Transfer {transfer_number} from {source_pharmacy.name}", db=db,
        )

        db.add(StockTransferItem(
            transfer_id=transfer.id, product_sku=source_product.sku, product_name=source_product.name,
            batch_number=source_batch.batch_number, expiry_date=source_batch.expiry_date,
            quantity=item.quantity, cost_price_paise=source_batch.cost_price_paise,
            mrp_paise=source_batch.mrp_paise, source_batch_id=source_batch.id,
            destination_batch_id=destination_batch.id,
        ))
        transferred_items.append({
            "product_sku": source_product.sku, "product_name": source_product.name,
            "batch_number": source_batch.batch_number, "quantity": item.quantity,
        })

    audit_values = {
        "transfer_number": transfer_number, "destination": destination_pharmacy.name, "items": transferred_items,
    }
    await _record_audit(
        source_pharmacy_id, uuid.UUID(current_user.id), "stock_transfer_out",
        transfer.id, audit_values, db, ip_address=_client_ip(request),
    )
    await _record_audit(
        destination_pharmacy_id, uuid.UUID(current_user.id), "stock_transfer_in",
        transfer.id, {**audit_values, "source": source_pharmacy.name}, db, ip_address=_client_ip(request),
    )
    await db.flush()

    return {
        "id": str(transfer.id), "transfer_number": transfer_number,
        "source_pharmacy": source_pharmacy.name, "destination_pharmacy": destination_pharmacy.name,
        "is_cross_gstin": is_cross_gstin, "items": transferred_items,
    }


@router.get("/stock-transfers")
async def list_stock_transfers(
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    """Every transfer where the caller's own pharmacy is either the
    source or the destination.
    # permission-exempt: read-only, tenant-scoped to the caller's own
    # pharmacy on either side of the transfer
    """
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(
        select(StockTransfer)
        .where(or_(StockTransfer.source_pharmacy_id == pharmacy_id,
                   StockTransfer.destination_pharmacy_id == pharmacy_id))
        .order_by(StockTransfer.created_at.desc())
    )
    transfers = result.scalars().all()

    pharmacy_ids = {t.source_pharmacy_id for t in transfers} | {t.destination_pharmacy_id for t in transfers}
    names_result = await db.execute(select(PharmacyORM.id, PharmacyORM.name).where(PharmacyORM.id.in_(pharmacy_ids)))
    names = {pid: name for pid, name in names_result.all()}

    return [{
        "id": str(t.id), "transfer_number": t.transfer_number,
        "source_pharmacy": names.get(t.source_pharmacy_id),
        "destination_pharmacy": names.get(t.destination_pharmacy_id),
        "direction": "out" if t.source_pharmacy_id == pharmacy_id else "in",
        "transfer_date": t.transfer_date.isoformat(), "is_cross_gstin": t.is_cross_gstin,
        "reversed": t.reversed_at is not None,
    } for t in transfers]


@router.post("/stock-transfers/{transfer_id}/reverse")
async def reverse_stock_transfer(
    transfer_id: str, request: Request,
    current_user: User = Depends(get_current_user), db: AsyncSession = DbSession,
):
    await require_admin_or_super(current_user, db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    try:
        transfer_uuid = uuid.UUID(transfer_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Transfer not found")

    # tenant-safe: scoped to a transfer where the caller's own pharmacy is
    # the source or the destination — never an arbitrary transfer id
    result = await db.execute(
        select(StockTransfer).where(
            StockTransfer.id == transfer_uuid,
            or_(StockTransfer.source_pharmacy_id == pharmacy_id,
                StockTransfer.destination_pharmacy_id == pharmacy_id)))
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.reversed_at is not None:
        raise HTTPException(status_code=400, detail="This transfer has already been reversed")

    items_result = await db.execute(select(StockTransferItem).where(StockTransferItem.transfer_id == transfer.id))
    items = items_result.scalars().all()

    for item in items:
        destination_batch = (await db.execute(
            # tenant-safe: id is from a StockTransferItem of the already-scoped `transfer`
            select(BatchORM).where(BatchORM.id == item.destination_batch_id))).scalar_one()
        source_batch = (await db.execute(
            # tenant-safe: id is from a StockTransferItem of the already-scoped `transfer`
            select(BatchORM).where(BatchORM.id == item.source_batch_id))).scalar_one()

        if destination_batch.quantity_on_hand < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reverse — some of batch {item.batch_number} has already "
                       f"been used at the destination store")

        destination_before = destination_batch.quantity_on_hand
        destination_batch.quantity_on_hand -= item.quantity
        source_before = source_batch.quantity_on_hand
        source_batch.quantity_on_hand += item.quantity

        await _record_movement(
            pharmacy_id=transfer.destination_pharmacy_id, product_id=destination_batch.product_id,
            batch_id=destination_batch.id, movement_type="transfer_reversal", quantity=-item.quantity,
            qty_before=destination_before, qty_after=destination_batch.quantity_on_hand,
            reference_id=transfer.id, user_id=uuid.UUID(current_user.id),
            notes=f"Reversal of transfer {transfer.transfer_number}", db=db,
        )
        await _record_movement(
            pharmacy_id=transfer.source_pharmacy_id, product_id=source_batch.product_id,
            batch_id=source_batch.id, movement_type="transfer_reversal", quantity=item.quantity,
            qty_before=source_before, qty_after=source_batch.quantity_on_hand,
            reference_id=transfer.id, user_id=uuid.UUID(current_user.id),
            notes=f"Reversal of transfer {transfer.transfer_number}", db=db,
        )

    transfer.reversed_at = datetime.now(timezone.utc)
    transfer.reversed_by = uuid.UUID(current_user.id)

    reversal_values = {"transfer_number": transfer.transfer_number}
    await _record_audit(
        transfer.source_pharmacy_id, uuid.UUID(current_user.id), "stock_transfer_reversed",
        transfer.id, reversal_values, db, ip_address=_client_ip(request),
    )
    await _record_audit(
        transfer.destination_pharmacy_id, uuid.UUID(current_user.id), "stock_transfer_reversed",
        transfer.id, reversal_values, db, ip_address=_client_ip(request),
    )
    await db.flush()

    return {"message": "Transfer reversed"}
