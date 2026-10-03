"""JSON shapes returned by the Patient Billing API."""
from __future__ import annotations

from modules.patient_billing.models import PbChargeItem, PbInvoice, PbPayment


def charge_dict(c: PbChargeItem) -> dict:
    return {
        "id": str(c.id), "patient_id": str(c.patient_id), "patient_name": c.patient_name,
        "patient_uhid": c.patient_uhid, "source_module": c.source_module, "source_ref": c.source_ref,
        "encounter_ref": c.encounter_ref, "encounter_type": c.encounter_type,
        "description": c.description, "quantity": c.quantity, "unit_price_paise": c.unit_price_paise,
        "total_paise": c.total_paise, "status": c.status,
        "invoice_id": str(c.invoice_id) if c.invoice_id else None, "void_reason": c.void_reason,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def invoice_dict(i: PbInvoice) -> dict:
    return {
        "id": str(i.id), "patient_id": str(i.patient_id), "patient_name": i.patient_name,
        "patient_uhid": i.patient_uhid, "invoice_number": i.invoice_number, "counter": i.counter,
        "status": i.status, "gross_paise": i.gross_paise, "discount_paise": i.discount_paise,
        "net_paise": i.net_paise, "paid_paise": i.paid_paise,
        "balance_paise": 0 if i.status == "cancelled" else i.net_paise - i.paid_paise,
        "lines": i.lines, "cancel_reason": i.cancel_reason,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def payment_dict(p: PbPayment, invoice_number: str | None = None, patient_name: str | None = None,
                 patient_uhid: str | None = None) -> dict:
    return {
        "id": str(p.id), "patient_id": str(p.patient_id), "invoice_id": str(p.invoice_id),
        "invoice_number": invoice_number, "patient_name": patient_name, "patient_uhid": patient_uhid,
        "amount_paise": p.amount_paise, "mode": p.mode,
        "reference": p.reference, "receipt_number": p.receipt_number, "paid_on": p.paid_on.isoformat(),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
