"""Shared constants — DEFAULT_ROLES, ALL_PERMISSIONS, and other app-wide values."""
from __future__ import annotations

# ── Default roles seeded at startup ───────────────────────────────────────────
DEFAULT_ROLES = [
    {
        "name": "admin",
        "display_name": "Administrator",
        "permissions": ["*"],
        "is_default": True,
        "is_super_admin": True,
    },
    {
        "name": "manager",
        "display_name": "Manager",
        "permissions": [
            "dashboard:view", "billing:create", "billing:view", "billing:edit",
            "inventory:view", "inventory:edit", "inventory:create", "inventory:batches_view",
            "inventory:batches_create", "inventory:stock_adjust",
            "purchases:create", "purchases:view", "purchases:edit", "purchase_returns:create",
            "purchase_returns:view", "sales_returns:create", "sales_returns:view",
            "customers:view", "customers:edit", "customers:create", "reports:view",
            "suppliers:view", "suppliers:create", "suppliers:edit", "suppliers:deactivate",
        ],
        "is_default": True,
        "is_super_admin": False,
    },
    {
        "name": "cashier",
        "display_name": "Cashier",
        "permissions": [
            "dashboard:view", "billing:create", "billing:view", "inventory:view",
            "sales_returns:create", "sales_returns:view", "customers:view",
            "customers:edit", "customers:create",
        ],
        "is_default": True,
        "is_super_admin": False,
    },
    {
        "name": "inventory_staff",
        "display_name": "Inventory Staff",
        "permissions": [
            "dashboard:view", "inventory:view", "inventory:edit", "inventory:create",
            "inventory:batches_view", "inventory:batches_create", "inventory:stock_adjust",
            "purchases:create", "purchases:view", "purchase_returns:create",
            "purchase_returns:view", "suppliers:view", "suppliers:create",
        ],
        "is_default": True,
        "is_super_admin": False,
    },
    {
        "name": "receptionist",
        "display_name": "Receptionist (EMR)",
        "permissions": [
            "patients:view", "patients:create", "patients:edit",
            "appointments:view", "appointments:create", "appointments:edit", "appointments:cancel",
            "schedules:view",
        ],
        "is_default": True,
        "is_super_admin": False,
    },
    {
        "name": "doctor",
        "display_name": "Doctor (EMR)",
        "permissions": [
            "patients:view", "patients:create", "patients:edit",
            "appointments:view", "appointments:create", "appointments:edit",
            "schedules:view", "schedules:edit",
        ],
        "is_default": True,
        "is_super_admin": False,
    },
]

# ── All permission definitions (used by /permissions endpoint and UI) ─────────
ALL_PERMISSIONS = {
    "dashboard": {"display_name": "Dashboard", "permissions": [
        {"id": "dashboard:view", "name": "View Dashboard"},
    ]},
    "billing": {"display_name": "Billing", "permissions": [
        {"id": "billing:create", "name": "Create Bills"},
        {"id": "billing:view", "name": "View Bills"},
        {"id": "billing:edit", "name": "Edit Bills"},
        {"id": "billing:delete", "name": "Delete Bills"},
    ]},
    "inventory": {"display_name": "Inventory", "permissions": [
        {"id": "inventory:view", "name": "View Inventory"},
        {"id": "inventory:create", "name": "Add Products"},
        {"id": "inventory:edit", "name": "Edit Products"},
        {"id": "inventory:delete", "name": "Delete Products"},
        {"id": "inventory:batches_view", "name": "View Batches"},
        {"id": "inventory:batches_create", "name": "Add Batches"},
        {"id": "inventory:stock_adjust", "name": "Adjust Stock"},
    ]},
    "purchases": {"display_name": "Purchases", "permissions": [
        {"id": "purchases:create", "name": "Create Purchases"},
        {"id": "purchases:view", "name": "View Purchases"},
        {"id": "purchases:edit", "name": "Edit Purchases"},
        {"id": "purchases:delete", "name": "Delete Purchases"},
    ]},
    "purchase_returns": {"display_name": "Purchase Returns", "permissions": [
        {"id": "purchase_returns:create", "name": "Create Returns"},
        {"id": "purchase_returns:view", "name": "View Returns"},
        {"id": "purchase_returns:confirm", "name": "Confirm Returns"},
    ]},
    "sales_returns": {"display_name": "Sales Returns", "permissions": [
        {"id": "sales_returns:create", "name": "Create Returns"},
        {"id": "sales_returns:view", "name": "View Returns"},
        {"id": "sales_returns:process", "name": "Process Returns"},
    ]},
    "customers": {"display_name": "Customers", "permissions": [
        {"id": "customers:view", "name": "View Customers"},
        {"id": "customers:create", "name": "Add Customers"},
        {"id": "customers:edit", "name": "Edit Customers"},
        {"id": "customers:delete", "name": "Delete Customers"},
    ]},
    "reports": {"display_name": "Reports", "permissions": [
        {"id": "reports:view", "name": "View Reports"},
        {"id": "reports:export", "name": "Export Reports"},
    ]},
    "settings": {"display_name": "Settings", "permissions": [
        {"id": "settings:view", "name": "View Settings"},
        {"id": "settings:edit", "name": "Edit Settings"},
    ]},
    "users": {"display_name": "User Management", "permissions": [
        {"id": "users:view", "name": "View Users"},
        {"id": "users:create", "name": "Create Users"},
        {"id": "users:edit", "name": "Edit Users"},
        {"id": "users:delete", "name": "Deactivate Users"},
    ]},
    "roles": {"display_name": "Roles & Permissions", "permissions": [
        {"id": "roles:view", "name": "View Roles"},
        {"id": "roles:create", "name": "Create Roles"},
        {"id": "roles:edit", "name": "Edit Roles"},
        {"id": "roles:delete", "name": "Delete Roles"},
    ]},
    "patients": {"display_name": "Patients (EMR)", "permissions": [
        {"id": "patients:view", "name": "View Patients"},
        {"id": "patients:create", "name": "Register Patients"},
        {"id": "patients:edit", "name": "Edit Patients"},
        {"id": "patients:delete", "name": "Delete Patients"},
    ]},
    "appointments": {"display_name": "Appointments (EMR)", "permissions": [
        {"id": "appointments:view", "name": "View Appointments & Queue"},
        {"id": "appointments:create", "name": "Book Appointments"},
        {"id": "appointments:edit", "name": "Reschedule / Update Appointments"},
        {"id": "appointments:cancel", "name": "Cancel Appointments"},
    ]},
    "schedules": {"display_name": "Doctor Schedules (EMR)", "permissions": [
        {"id": "schedules:view", "name": "View Doctor Schedules"},
        {"id": "schedules:edit", "name": "Edit Doctor Schedules"},
    ]},
    "suppliers": {"display_name": "Suppliers", "permissions": [
        {"id": "suppliers:view", "name": "View Suppliers"},
        {"id": "suppliers:create", "name": "Create Suppliers"},
        {"id": "suppliers:edit", "name": "Edit Suppliers"},
        {"id": "suppliers:deactivate", "name": "Deactivate Suppliers"},
    ]},
}

# ── Product category → HSN mapping ─────────────────────────────────────────────
# HSN is government-fixed, not something a pharmacist should type per product —
# a retail pharmacy only ever needs these four codes. Category picks the HSN
# automatically so the same kind of product can never end up with two different
# codes depending on who added it.
PRODUCT_CATEGORIES = [
    {"value": "medicine", "label": "Medicine", "hsn_code": "3004",
     "hsn_description": "Tablets, capsules, syrups, injections, ointments, drops"},
    {"value": "surgical", "label": "Surgical", "hsn_code": "3005",
     "hsn_description": "Bandages, gauze, cotton, dressings"},
    {"value": "first_aid", "label": "First Aid / Contraceptive", "hsn_code": "3006",
     "hsn_description": "First-aid kits, contraceptives, diagnostic reagents"},
    {"value": "device", "label": "Medical Device", "hsn_code": "9018",
     "hsn_description": "Syringes, glucometers, BP monitors, thermometers"},
]
CATEGORY_HSN_MAP = {c["value"]: c["hsn_code"] for c in PRODUCT_CATEGORIES}
VALID_CATEGORIES = set(CATEGORY_HSN_MAP)

# GST slabs that actually apply to pharmacy products (28% doesn't).
VALID_GST_RATES = {0, 5, 12, 18}

# Dosage form decides whether a product can be sold loose (one tablet out of a
# strip) or only as a whole pack (a syrup bottle can't be subdivided).
DOSAGE_FORMS = [
    {"value": "tablet", "label": "Tablet", "divisible": True},
    {"value": "capsule", "label": "Capsule", "divisible": True},
    {"value": "syrup", "label": "Syrup / Liquid", "divisible": False},
    {"value": "injection", "label": "Injection", "divisible": False},
    {"value": "ointment", "label": "Ointment / Cream", "divisible": False},
    {"value": "drops", "label": "Drops", "divisible": False},
    {"value": "powder", "label": "Powder / Sachet", "divisible": False},
    {"value": "inhaler", "label": "Inhaler", "divisible": False},
    {"value": "other", "label": "Other", "divisible": False},
]
VALID_DOSAGE_FORMS = {d["value"] for d in DOSAGE_FORMS}
