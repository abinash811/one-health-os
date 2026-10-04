"""Patient Billing's say in switching a clinic off: no money may be left unbilled or unpaid."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.patient_billing.constants import CHG_UNBILLED, INVOICE_OPEN_STATUSES
from modules.patient_billing.models import PbChargeItem, PbInvoice
from services.clinic_guards import register_clinic_guard


@register_clinic_guard
async def unsettled_money(db: AsyncSession, clinic_id: uuid.UUID) -> Optional[str]:
    unbilled = (await db.execute(select(func.count()).select_from(PbChargeItem).where(
        PbChargeItem.clinic_id == clinic_id, PbChargeItem.status == CHG_UNBILLED,
        PbChargeItem.deleted_at.is_(None)))).scalar_one()
    open_inv = (await db.execute(select(func.count()).select_from(PbInvoice).where(
        PbInvoice.clinic_id == clinic_id, PbInvoice.status.in_(INVOICE_OPEN_STATUSES),
        PbInvoice.deleted_at.is_(None)))).scalar_one()
    if unbilled or open_inv:
        parts = []
        if unbilled:
            parts.append(f"{unbilled} charge{'s' if unbilled != 1 else ''} not yet billed")
        if open_inv:
            parts.append(f"{open_inv} bill{'s' if open_inv != 1 else ''} not fully paid")
        return " and ".join(parts) + " — settle them first"
    return None
