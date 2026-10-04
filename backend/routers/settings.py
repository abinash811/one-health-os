from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import ALL_PERMISSIONS, DEFAULT_ROLES  # noqa: F401 — DEFAULT_ROLES re-exported for main.py
from deps import DbSession
from models.billing import Bill, SalesReturn
from models.pharmacy import Pharmacy, PharmacySettings
from models.users import AuditLog, Role as RoleORM
from services.role_scope import chain_of, find_role, get_role_or_404, list_roles, role_users_in_chain
from routers.auth_helpers import User, get_current_user, require_admin_or_super

router = APIRouter(prefix="/api", tags=["settings"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


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


# Every PharmacySettings/Pharmacy column update_settings() can write to —
# used to snapshot before/after and log only the fields that actually
# changed. Kept as one explicit list rather than instrumenting each
# individual `setattr` call below, so a future field added to one of the
# request models can't silently skip audit logging by omission.
_SETTINGS_TRACKED_FIELDS = [
    "near_expiry_threshold_days", "low_stock_threshold_days", "block_expired_stock",
    "allow_near_expiry_sale", "alert_low_stock_enabled", "alert_near_expiry_enabled",
    "alert_drug_license_enabled", "drug_license_alert_days",
    "paper_size", "print_logo", "print_drug_license", "print_patient_name",
    "bill_header", "bill_footer", "print_signature", "print_gstin", "print_fssai", "print_pan",
    "digital_use_default_header", "digital_header_image_url", "digital_footer_image_url",
    "digital_header_height_px", "digital_footer_height_px", "digital_bill_header", "digital_bill_footer",
    "default_gst_rate", "default_hsn_medicines", "default_hsn_surgical", "auto_apply_hsn",
    "round_off_amount", "print_gst_summary",
    "enable_draft_bills", "auto_print_invoice",
    "return_window_days", "require_original_bill", "allow_partial_return",
]
_PHARMACY_TRACKED_FIELDS = [
    "name", "address", "city", "state", "pincode", "phone", "email", "gstin",
    "drug_license_number", "drug_license_expiry", "fssai_number", "pan_number", "logo_url",
]


def _serialize_setting_value(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _snapshot_settings_fields(ps: Optional[PharmacySettings], pharmacy: Optional[Pharmacy]) -> dict:
    snapshot = {f: _serialize_setting_value(getattr(ps, f, None)) for f in _SETTINGS_TRACKED_FIELDS}
    snapshot.update(
        {f: _serialize_setting_value(getattr(pharmacy, f, None)) for f in _PHARMACY_TRACKED_FIELDS})
    return snapshot


# ── Pydantic request models ──────────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str
    display_name: str
    permissions: List[str]


class RoleUpdate(BaseModel):
    display_name: Optional[str] = None
    permissions: Optional[List[str]] = None


class BillSequenceSettings(BaseModel):
    # "sales_invoice" | "sales_return" — see SEQUENCE_DOCUMENT_TYPE in
    # domainConstants.js. Each is its own gapless number series (GST Rule 46).
    document_type: str = "sales_invoice"
    prefix: str = "INV"
    starting_number: int = 1
    sequence_length: int = 6
    allow_prefix_change: bool = True


# document_type -> (PharmacySettings prefix/seq/length attrs,
# doc model, doc number column, human label)
_SEQUENCE_TYPES = {
    "sales_invoice": (
        "bill_prefix", "bill_sequence_number", "bill_number_length",
        Bill, "bill_number", "Sales Invoice",
    ),
    "sales_return": (
        "return_prefix", "return_sequence_number", "return_number_length",
        SalesReturn, "return_number", "Sales Return",
    ),
}


class DigitalReceiptUpdate(BaseModel):
    """Validates the 'digital' section of PUT /settings — the shareable,
    screen-viewed receipt template (WhatsApp/email/download). Always one
    fixed A4-style layout; unlike Print, there is no paper-size choice here.
    """
    use_default_header: Optional[bool] = None
    header_image_url: Optional[str] = None
    footer_image_url: Optional[str] = None
    header_height_px: Optional[int] = None
    footer_height_px: Optional[int] = None
    header_text: Optional[str] = None
    footer_text: Optional[str] = None

    @field_validator("header_height_px", "footer_height_px")
    @classmethod
    def height_in_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (20 <= v <= 400):
            raise ValueError("Height must be between 20 and 400 pixels")
        return v


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")
PINCODE_RE = re.compile(r"^\d{6}$")


class PharmacyGeneralUpdate(BaseModel):
    """Validates the pharmacy-profile section of PUT /settings.

    The frontend (PharmacyProfileTab.tsx) already checks these formats, but
    that alone never stopped a direct API call from saving garbage — this is
    the actual enforcement.
    """
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gstin: Optional[str] = None
    drug_license_number: Optional[str] = None
    drug_license_expiry: Optional[date] = None
    fssai_number: Optional[str] = None
    pan_number: Optional[str] = None
    logo_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: Optional[str]) -> Optional[str]:
        # Only Pharmacy Name is required to save this page. Phone and the
        # full address (street/city/state/pincode) are recommended — shown
        # on printed bills — but a pharmacy can save the page without them
        # and fill them in later.
        if v is not None and not v.strip():
            raise ValueError("Pharmacy Name cannot be blank")
        return v

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: Optional[str]) -> Optional[str]:
        if v and not PHONE_RE.match(v):
            raise ValueError("Phone must be a valid 10-digit Indian mobile number")
        return v

    @field_validator("pincode")
    @classmethod
    def valid_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v and not PINCODE_RE.match(v):
            raise ValueError("Pincode must be 6 digits")
        return v

    @field_validator("gstin")
    @classmethod
    def valid_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip().upper()
            if not GSTIN_RE.match(v):
                raise ValueError("Invalid GSTIN format")
        return v

    @field_validator("pan_number")
    @classmethod
    def valid_pan(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip().upper()
            if not PAN_RE.match(v):
                raise ValueError("Invalid PAN format (e.g. ABCDE1234F)")
        return v

    @field_validator("drug_license_expiry", mode="before")
    @classmethod
    def blank_expiry_to_none(cls, v):
        # The date <input> sends "" when cleared — treat that as "no date",
        # not a parse error.
        return None if v == "" else v


# ── helpers ───────────────────────────────────────────────────────────────────

def _validation_errors(e: ValidationError) -> list:
    """Turn a Pydantic ValidationError into [{field, message}, ...] for a 422
    response. Pydantic v2 prefixes a raised ValueError's text with "Value
    error, " — strip that; it's implementation detail, not something a
    pharmacist reading a toast needs to see.
    """
    errors = []
    for err in e.errors():
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        errors.append({"field": err["loc"][-1], "message": msg})
    return errors


def _role_response(role: RoleORM) -> dict:
    perms = role.permissions if isinstance(role.permissions, list) else []
    return {
        "id": str(role.id),
        "name": role.name,
        "display_name": role.description or role.name.replace("_", " ").title(),
        "permissions": perms,
        "is_default": role.is_system_role,
        "is_super_admin": "*" in perms,
        "is_active": role.is_active,
        "created_at": role.created_at.isoformat() if role.created_at else None,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
    }


# ── /settings ─────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_user),
                       db: AsyncSession = DbSession):
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = result.scalar_one_or_none()

    pharm_result = await db.execute(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
    pharmacy = pharm_result.scalar_one_or_none()

    return {
        "inventory": {
            "near_expiry_days": ps.near_expiry_threshold_days if ps else 90,
            "low_stock_threshold_days": ps.low_stock_threshold_days if ps else 30,
            "block_expired_stock": ps.block_expired_stock if ps else True,
            "allow_near_expiry_sale": ps.allow_near_expiry_sale if ps else True,
            # Same real column as notifications.alert_low_stock_enabled below —
            # this tab shows the same setting under its own label, matching
            # how near_expiry_days is already shown in both tabs.
            "low_stock_alert_enabled": ps.alert_low_stock_enabled if ps else True,
        },
        "notifications": {
            "alert_low_stock_enabled": ps.alert_low_stock_enabled if ps else True,
            "alert_near_expiry_enabled": ps.alert_near_expiry_enabled if ps else True,
            "alert_drug_license_enabled": ps.alert_drug_license_enabled if ps else True,
            "low_stock_threshold_days": ps.low_stock_threshold_days if ps else 30,
            "near_expiry_days": ps.near_expiry_threshold_days if ps else 90,
            "drug_license_alert_days": ps.drug_license_alert_days if ps else 90,
        },
        "billing": {
            "enable_draft_bills": ps.enable_draft_bills if ps else True,
            "auto_print_invoice": ps.auto_print_invoice if ps else False,
            "bill_prefix": ps.bill_prefix if ps else "INV",
            "bill_sequence_number": ps.bill_sequence_number if ps else 1,
            "bill_number_length": ps.bill_number_length if ps else 6,
        },
        "returns": {
            "return_window_days": ps.return_window_days if ps else 7,
            "require_original_bill": ps.require_original_bill if ps else False,
            "allow_partial_return": ps.allow_partial_return if ps else True,
        },
        "general": {
            "name": pharmacy.name if pharmacy else "",
            "address": pharmacy.address if pharmacy else "",
            "city": pharmacy.city if pharmacy else "",
            "state": pharmacy.state if pharmacy else "",
            "pincode": pharmacy.pincode if pharmacy else "",
            "phone": pharmacy.phone if pharmacy else "",
            "email": pharmacy.email if pharmacy else "",
            "gstin": pharmacy.gstin if pharmacy else "",
            "drug_license_number": pharmacy.drug_license_number if pharmacy else "",
            "drug_license_expiry": (
                pharmacy.drug_license_expiry.isoformat()
                if pharmacy and pharmacy.drug_license_expiry else ""
            ),
            "fssai_number": pharmacy.fssai_number if pharmacy else "",
            "pan_number": pharmacy.pan_number if pharmacy else "",
            "logo_url": pharmacy.logo_url if pharmacy else "",
        },
        "gst": {
            "default_gst_rate": float(ps.default_gst_rate) if ps else 5.0,
            "default_hsn_medicines": ps.default_hsn_medicines if ps else "3004",
            "default_hsn_surgical": ps.default_hsn_surgical if ps else "9018",
            "auto_apply_hsn": ps.auto_apply_hsn if ps else True,
            "round_off_amount": ps.round_off_amount if ps else True,
            "print_gst_summary": ps.print_gst_summary if ps else True,
        },
        "print": {
            "paper_size": ps.paper_size if ps else "80mm",
            "print_logo": ps.print_logo if ps else True,
            "print_drug_license": ps.print_drug_license if ps else True,
            "print_patient_name": ps.print_patient_name if ps else True,
            "print_gstin": ps.print_gstin if ps else True,
            "print_fssai": ps.print_fssai if ps else False,
            "print_signature": ps.print_signature if ps else False,
            "print_pan": ps.print_pan if ps else False,
            # Both fall back to a real default whenever the pharmacy hasn't
            # set its own text yet — not just when the settings row itself
            # doesn't exist. bill_header previously defaulted to "" even
            # once a settings row existed with the field still unset, so
            # every invoice/receipt/PDF silently printed no header at all
            # until a pharmacy discovered and filled in this field.
            "bill_header": (ps.bill_header if ps else None) or "This is a computer-generated invoice.",
            "bill_footer": (ps.bill_footer if ps else None) or "Thank you for your purchase!",
        },
        "digital": {
            "use_default_header": ps.digital_use_default_header if ps else True,
            "header_image_url": ps.digital_header_image_url if ps else "",
            "footer_image_url": ps.digital_footer_image_url if ps else "",
            "header_height_px": ps.digital_header_height_px if ps else 100,
            "footer_height_px": ps.digital_footer_height_px if ps else 60,
            "header_text": ps.digital_bill_header if ps else "",
            "footer_text": ps.digital_bill_footer if ps else "",
        },
    }


@router.put("/settings")
async def update_settings(settings_data: dict, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)

    pharmacy_id = uuid.UUID(current_user.pharmacy_id)

    # ── PharmacySettings (inventory / print / gst) ────────────────────────────
    result = await db.execute(select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = result.scalar_one_or_none()
    if not ps:
        ps = PharmacySettings(pharmacy_id=pharmacy_id)
        db.add(ps)

    pharm_result = await db.execute(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
    pharmacy = pharm_result.scalar_one_or_none()

    # Settings had zero audit-log coverage — a real business-rule change
    # (a GST rate, a return window, a billing default) left no trace of
    # who changed what, when. Snapshot before any section below mutates
    # ps/pharmacy; diffed against the after-snapshot once every section
    # has applied, so only fields that actually changed get logged.
    before_settings = _snapshot_settings_fields(ps, pharmacy)

    # near_expiry_days and low_stock_alert_enabled below are ALSO written by
    # the "notifications" section right after this one — both tabs edit the
    # same PharmacySettings column on purpose (Inventory groups "rules",
    # Notifications groups "alerts" with live previews). The frontend
    # (Settings/hooks/useSettings.js's MIRRORED_FIELDS) keeps both copies of
    # its local state in sync the moment either is edited, so by the time a
    # save reaches here both sections already agree and this fixed
    # processing order is safe. Found Sep 28, 2026 (docs/15_ROADMAP.md RULE
    # MISSES LOG): before that frontend fix, editing only one tab's copy
    # left the other tab's stale value in the same full-object PUT, and
    # notifications' stale value silently overwrote whatever was just
    # changed on Inventory every time, regardless of which tab the user
    # actually edited. Adding a new mirrored field here without the
    # matching frontend sync would reintroduce the same bug.
    inv = settings_data.get("inventory", {})
    if "near_expiry_days" in inv:
        ps.near_expiry_threshold_days = inv["near_expiry_days"]
    if "low_stock_threshold_days" in inv:
        ps.low_stock_threshold_days = inv["low_stock_threshold_days"]
    if "block_expired_stock" in inv:
        ps.block_expired_stock = inv["block_expired_stock"]
    if "allow_near_expiry_sale" in inv:
        ps.allow_near_expiry_sale = inv["allow_near_expiry_sale"]
    if "low_stock_alert_enabled" in inv:
        ps.alert_low_stock_enabled = inv["low_stock_alert_enabled"]

    notif = settings_data.get("notifications", {})
    for field in ["alert_low_stock_enabled", "alert_near_expiry_enabled",
                  "alert_drug_license_enabled", "drug_license_alert_days"]:
        if field in notif:
            setattr(ps, field, notif[field])
    if "low_stock_threshold_days" in notif:
        ps.low_stock_threshold_days = notif["low_stock_threshold_days"]
    if "near_expiry_days" in notif:
        ps.near_expiry_threshold_days = notif["near_expiry_days"]

    printing = settings_data.get("print", {})
    if "paper_size" in printing:
        ps.paper_size = printing["paper_size"]
    if "print_logo" in printing:
        ps.print_logo = printing["print_logo"]
    if "print_drug_license" in printing:
        ps.print_drug_license = printing["print_drug_license"]
    if "print_patient_name" in printing:
        ps.print_patient_name = printing["print_patient_name"]
    if "bill_header" in printing:
        ps.bill_header = printing["bill_header"]
    if "bill_footer" in printing:
        ps.bill_footer = printing["bill_footer"]
    if "print_signature" in printing:
        ps.print_signature = printing["print_signature"]
    if "print_gstin" in printing:
        ps.print_gstin = printing["print_gstin"]
    if "print_fssai" in printing:
        ps.print_fssai = printing["print_fssai"]
    if "print_pan" in printing:
        ps.print_pan = printing["print_pan"]

    digital = settings_data.get("digital", {})
    if digital:
        try:
            digital_validated = DigitalReceiptUpdate(**digital)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=_validation_errors(e))
        field_map = {
            "use_default_header": "digital_use_default_header",
            "header_image_url": "digital_header_image_url",
            "footer_image_url": "digital_footer_image_url",
            "header_height_px": "digital_header_height_px",
            "footer_height_px": "digital_footer_height_px",
            "header_text": "digital_bill_header",
            "footer_text": "digital_bill_footer",
        }
        for api_field, model_field in field_map.items():
            value = getattr(digital_validated, api_field)
            if api_field in digital and value is not None:
                setattr(ps, model_field, value)

    gst = settings_data.get("gst", {})
    for field in ["default_gst_rate", "default_hsn_medicines",
                  "default_hsn_surgical", "auto_apply_hsn",
                  "round_off_amount", "print_gst_summary"]:
        if field in gst:
            setattr(ps, field, gst[field])

    # Billing / Returns preferences — found Sep 13, 2026 (Settings
    # product-review): GET previously returned hardcoded constants for both
    # and PUT never processed either section at all, so a save here silently
    # did nothing. See docs/15_ROADMAP.md.
    billing_prefs = settings_data.get("billing", {})
    if "enable_draft_bills" in billing_prefs:
        ps.enable_draft_bills = billing_prefs["enable_draft_bills"]
    if "auto_print_invoice" in billing_prefs:
        ps.auto_print_invoice = billing_prefs["auto_print_invoice"]

    returns_prefs = settings_data.get("returns", {})
    if "return_window_days" in returns_prefs:
        ps.return_window_days = returns_prefs["return_window_days"]
    if "require_original_bill" in returns_prefs:
        ps.require_original_bill = returns_prefs["require_original_bill"]
    if "allow_partial_return" in returns_prefs:
        ps.allow_partial_return = returns_prefs["allow_partial_return"]

    # ── Pharmacy profile ──────────────────────────────────────────────────────
    general = settings_data.get("general", {})
    if general:
        try:
            validated = PharmacyGeneralUpdate(**general)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=_validation_errors(e))

        if pharmacy:
            for field in ["name", "address", "city", "state", "pincode", "phone", "email",
                          "gstin", "drug_license_number", "drug_license_expiry",
                          "fssai_number", "pan_number", "logo_url"]:
                value = getattr(validated, field)
                if field in general and value is not None:
                    setattr(pharmacy, field, value)

    after_settings = _snapshot_settings_fields(ps, pharmacy)
    changed_old = {f: v for f, v in before_settings.items() if after_settings[f] != v}
    changed_new = {f: after_settings[f] for f in changed_old}
    if changed_new:
        await _record_audit(
            pharmacy_id, uuid.UUID(current_user.id), "update", "settings", pharmacy_id,
            changed_new, db, old_values=changed_old, ip_address=_client_ip(request),
        )

    await db.flush()
    return {"message": "Settings updated successfully"}


# ── /permissions ──────────────────────────────────────────────────────────────

@router.get("/permissions")
async def get_all_permissions(current_user: User = Depends(get_current_user),
                              db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    return ALL_PERMISSIONS


# ── /roles ────────────────────────────────────────────────────────────────────

@router.get("/roles")
async def get_all_roles(current_user: User = Depends(get_current_user),
                        db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    roles = await list_roles(db, uuid.UUID(current_user.pharmacy_id))
    return [_role_response(r) for r in roles]


@router.post("/roles")
async def create_role(role_data: RoleCreate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    if await find_role(db, pharmacy_id, role_data.name, active_only=False):
        raise HTTPException(status_code=400, detail="Role name already exists")

    role = RoleORM(
        pharmacy_id=pharmacy_id,
        chain_id=await chain_of(db, pharmacy_id),
        name=role_data.name,
        description=role_data.display_name,
        permissions=role_data.permissions,
        is_system_role=False,
    )
    db.add(role)
    await db.flush()
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "create", "role", role.id,
        {"name": role.name, "permissions": role.permissions}, db, ip_address=_client_ip(request),
    )
    await db.flush()
    return _role_response(role)


@router.get("/roles/{role_id}")
async def get_role(role_id: str, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    role = await get_role_or_404(db, role_id, uuid.UUID(current_user.pharmacy_id))
    return _role_response(role)


@router.put("/roles/{role_id}")
async def update_role(role_id: str, role_update: RoleUpdate, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    role = await get_role_or_404(db, role_id, uuid.UUID(current_user.pharmacy_id))
    if role.is_system_role:
        raise HTTPException(status_code=400, detail="Cannot edit default roles")

    old_values = {"display_name": role.description, "permissions": role.permissions}

    if role_update.display_name is not None:
        role.description = role_update.display_name
    if role_update.permissions is not None:
        role.permissions = role_update.permissions

    await db.flush()
    await db.refresh(role)  # updated_at has onupdate=func.now() — see purchases.py for the full note
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "update", "role", role.id,
        {"display_name": role.description, "permissions": role.permissions}, db,
        old_values=old_values, ip_address=_client_ip(request),
    )
    await db.flush()
    return _role_response(role)


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, request: Request, current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    role = await get_role_or_404(db, role_id, uuid.UUID(current_user.pharmacy_id))
    if role.is_system_role:
        raise HTTPException(status_code=400, detail="Cannot delete default roles")

    user_count = await role_users_in_chain(db, role.id)
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete role. {user_count} user(s) are assigned this role")

    role.is_active = False
    await db.flush()
    await _record_audit(
        uuid.UUID(current_user.pharmacy_id), uuid.UUID(current_user.id), "delete", "role", role.id,
        {"is_active": False}, db, old_values={"is_active": True}, ip_address=_client_ip(request),
    )
    await db.flush()
    return {"message": "Role deleted successfully"}


# ── /settings/bill-sequence ───────────────────────────────────────────────────

def _sequence_response(ps: Optional[PharmacySettings], document_type: str) -> dict:
    prefix_attr, seq_attr, length_attr, _model, _col, label = _SEQUENCE_TYPES[document_type]
    default_prefix = "INV" if document_type == "sales_invoice" else "CN"
    default_length = 6 if document_type == "sales_invoice" else 5
    prefix = getattr(ps, prefix_attr) if ps else default_prefix
    seq = getattr(ps, seq_attr) if ps else 1
    length = getattr(ps, length_attr) if ps else default_length
    return {
        "document_type": document_type,
        "label": label,
        "prefix": prefix,
        "current_sequence": seq - 1,
        "sequence_length": length,
        "allow_prefix_change": True,
        "next_number": seq,
    }


@router.get("/settings/bill-sequence")
async def get_bill_sequence_settings(
    document_type: str = "sales_invoice",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = DbSession,
):
    if document_type not in _SEQUENCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown document_type '{document_type}'")
    result = await db.execute(
        select(PharmacySettings).where(
            PharmacySettings.pharmacy_id == uuid.UUID(
                current_user.pharmacy_id))
    )
    return _sequence_response(result.scalar_one_or_none(), document_type)


@router.put("/settings/bill-sequence")
async def update_bill_sequence_settings(
        seq_settings: BillSequenceSettings,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = DbSession):
    await require_admin_or_super(current_user, db)
    if seq_settings.document_type not in _SEQUENCE_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unknown document_type '{seq_settings.document_type}'"
        )

    prefix_attr, seq_attr, length_attr, doc_model, doc_col, label = (
        _SEQUENCE_TYPES[seq_settings.document_type]
    )

    pharmacy_id = uuid.UUID(current_user.pharmacy_id)
    result = await db.execute(select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy_id))
    ps = result.scalar_one_or_none()

    # current_seq is the NEXT number that would be assigned, not the last used
    # one — keeping it unchanged (starting_number == current_seq) or moving it
    # forward is always safe. Only moving it backward risks reusing a number
    # that's already been issued.
    current_seq = getattr(ps, seq_attr) if ps else 1
    if ps and current_seq > seq_settings.starting_number:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Starting number must be at least the next number ({current_seq}) "
                f"for {label} prefix '{seq_settings.prefix}'"
            ),
        )

    doc_number_column = getattr(doc_model, doc_col)
    highest = await db.execute(
        select(doc_number_column)
        .where(
            doc_model.pharmacy_id == pharmacy_id,
            doc_number_column.like(f"{seq_settings.prefix}-%"),
        )
        .order_by(doc_number_column.desc())
        .limit(1)
    )
    highest_number = highest.scalar_one_or_none()
    if highest_number:
        try:
            parts = highest_number.split("-")
            if len(parts) >= 2 and int(parts[-1]) >= seq_settings.starting_number:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Starting number must be greater than highest existing "
                        f"{label} number ({int(parts[-1])}) for prefix '{seq_settings.prefix}'"
                    ),
                )
        except (ValueError, IndexError):
            pass

    if not ps:
        ps = PharmacySettings(pharmacy_id=pharmacy_id)
        db.add(ps)

    old_values = {"prefix": getattr(ps, prefix_attr, None), "starting_number": current_seq,
                  "sequence_length": getattr(ps, length_attr, None)}
    setattr(ps, prefix_attr, seq_settings.prefix)
    setattr(ps, seq_attr, seq_settings.starting_number)
    setattr(ps, length_attr, seq_settings.sequence_length)
    await db.flush()
    await _record_audit(
        pharmacy_id, uuid.UUID(current_user.id), "update", "bill_sequence", pharmacy_id,
        {"document_type": seq_settings.document_type, "prefix": seq_settings.prefix,
         "starting_number": seq_settings.starting_number, "sequence_length": seq_settings.sequence_length},
        db, old_values=old_values, ip_address=_client_ip(request),
    )
    await db.flush()

    return _sequence_response(ps, seq_settings.document_type)


@router.get("/settings/bill-sequence/all")
async def get_all_bill_sequences(current_user: User = Depends(
        get_current_user), db: AsyncSession = DbSession):
    result = await db.execute(
        select(PharmacySettings).where(
            PharmacySettings.pharmacy_id == uuid.UUID(
                current_user.pharmacy_id))
    )
    ps = result.scalar_one_or_none()
    return [_sequence_response(ps, document_type) for document_type in _SEQUENCE_TYPES]
