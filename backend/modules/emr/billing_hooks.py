"""EMR -> Patient Billing: the consultation fee.

EMR talks to billing ONLY through `modules.patient_billing.service` (the same
functions the billing HTTP API uses) — never its tables (docs/27 product
principle). The fee is a charge on the patient's account, posted when the
patient checks in, so the front desk can collect it straight away."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.users import User as UserORM
from modules.emr.common import _record_audit
from modules.emr.models import EmrAppointment, EmrDoctorProfile, EmrPatient
from modules.patient_billing import service as billing
from modules.patient_billing.constants import SRC_EMR


def _fee_key(appt: EmrAppointment) -> str:
    return f"emr:appointment:{appt.id}:consultation"


async def post_consultation_fee(db: AsyncSession, appt: EmrAppointment, user_id: uuid.UUID,
                                ip_address: str | None = None) -> None:
    """Posts the doctor's consultation fee for this visit. No fee set (or ₹0) = nothing posted.
    Safe to call twice: the idempotency key means one visit is only ever charged once."""
    profile = (await db.execute(select(EmrDoctorProfile).where(
        EmrDoctorProfile.pharmacy_id == appt.pharmacy_id,
        EmrDoctorProfile.user_id == appt.doctor_user_id))).scalar_one_or_none()
    fee = profile.consultation_fee_paise if profile else None
    if not fee:
        return
    patient = (await db.execute(select(EmrPatient).where(
        EmrPatient.id == appt.patient_id, EmrPatient.pharmacy_id == appt.pharmacy_id))).scalar_one()
    doctor = (await db.execute(select(UserORM.name).where(
        UserORM.id == appt.doctor_user_id, UserORM.pharmacy_id == appt.pharmacy_id))).scalar()
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
