"""EMR -> Patient Billing: the consultation fee.

EMR talks to billing ONLY through `modules.patient_billing.service` (the same
functions the billing HTTP API uses) — never its tables (docs/27 product
principle). The fee is a charge on the patient's account, posted when the
patient checks in, so the front desk can collect it straight away."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.emr.common import _record_audit
from modules.emr.doctors import clinic_fee_paise, doctor_for_record
from modules.emr.models import EmrAppointment, EmrPatient
from modules.patient_billing import service as billing
from modules.patient_billing.constants import CHG_PAID, CHG_VOID, INV_PART_PAID, SRC_EMR


def _fee_key(appt: EmrAppointment) -> str:
    return f"emr:appointment:{appt.id}:consultation"


async def post_consultation_fee(db: AsyncSession, appt: EmrAppointment, user_id: uuid.UUID,
                                ip_address: str | None = None) -> None:
    """Posts the doctor's consultation fee for this visit. No fee set (or ₹0) = nothing posted.
    Safe to call twice: the idempotency key means one visit is only ever charged once."""
    fee = await clinic_fee_paise(db, appt.pharmacy_id, appt.practitioner_id)   # this clinic's fee for this doctor
    if not fee:
        return
    patient = (await db.execute(select(EmrPatient).where(
        EmrPatient.id == appt.patient_id, EmrPatient.pharmacy_id == appt.pharmacy_id))).scalar_one()
    doctor = getattr(await doctor_for_record(db, appt.practitioner_id), "name", None)
    charge, created = await billing.post_charge(
        db, pharmacy_id=appt.pharmacy_id, user_id=user_id, patient_id=patient.id,
        patient_name=patient.name, patient_uhid=patient.uhid, source_module=SRC_EMR,
        description=f"Consultation — {doctor}" if doctor else "Consultation", unit_price_paise=fee,
        source_ref=str(appt.id), encounter_ref=str(appt.id), encounter_type="appointment",
        idempotency_key=_fee_key(appt))
    if created:
        await _record_audit(
            appt.pharmacy_id, user_id, "create", "pb_charge_item", charge.id,
            {"description": charge.description, "total_paise": charge.total_paise,
             "source_module": SRC_EMR, "appointment_id": str(appt.id)}, db, ip_address=ip_address)


async def withdraw_consultation_fee(db: AsyncSession, appt: EmrAppointment, user_id: uuid.UUID,
                                    reason: str, ip_address: str | None = None) -> None:
    """Visit cancelled: take the fee off the account — but only if it is still unbilled. Once an
    invoice exists, undoing it is a billing-desk decision (cancel the invoice / refund), not ours."""
    charge = await billing.void_unbilled_by_key(db, appt.pharmacy_id, _fee_key(appt), reason)
    if charge:
        await _record_audit(
            appt.pharmacy_id, user_id, "void", "pb_charge_item", charge.id,
            {"reason": reason, "total_paise": charge.total_paise, "appointment_id": str(appt.id)},
            db, ip_address=ip_address)


# What the queue shows next to each visit
FEE_UNPAID, FEE_PART_PAID, FEE_PAID = "unpaid", "part_paid", "paid"


async def fee_for_appointments(db: AsyncSession, pharmacy_id: uuid.UUID,
                               appts: list[EmrAppointment]) -> dict[uuid.UUID, dict]:
    """appointment id -> its consultation fee as the front desk sees it (amount, unpaid / part-paid /
    paid, who/how it was paid, and the invoice to collect against). Visits with no fee, or whose fee
    was withdrawn, are absent."""
    snaps = await billing.snapshots_by_key(db, pharmacy_id, [_fee_key(a) for a in appts])
    out = {}
    for a in appts:
        s = snaps.get(_fee_key(a))
        if not s or s["charge_status"] == CHG_VOID:
            continue
        if s["charge_status"] == CHG_PAID:
            status = FEE_PAID
        elif s["invoice_status"] == INV_PART_PAID:
            status = FEE_PART_PAID
        else:
            status = FEE_UNPAID
        out[a.id] = {
            "charge_id": s["charge_id"], "amount_paise": s["amount_paise"], "status": status,
            "paid_paise": s["paid_paise"], "balance_paise": 0 if status == FEE_PAID else s["balance_paise"],
            "mode": s["mode"], "invoice_id": s["invoice_id"], "invoice_number": s["invoice_number"]}
    return out
