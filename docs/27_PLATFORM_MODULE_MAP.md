# Platform vs. Module Map — Core vs. Pharmacy
# Version: 0.1 | Last updated: October 2, 2026
# Type: Explanation
# Status: Draft — mapping only, nothing built or moved yet.

Goal: one core platform (like Open Healthcare Network / CARE) + add-on
modules. Pharmacy = module #1, EMR = module #2.
Scope: mapping only. 🚫 Nothing here is built or moved yet.

## Core (shared by every module)

| Area | Where it lives today | Notes |
|------|----------------------|-------|
| Auth, JWT, password reset | `routers/auth.py`, `auth_helpers.py`, `models/users.py` | Generic already |
| Users, roles, permissions | `routers/users.py`, `settings.py` (roles part), `constants.py` (`DEFAULT_ROLES`, `ALL_PERMISSIONS`) | Permission list is pharmacy-flavoured — must become per-module, registered by each module |
| Tenant / chain / store scoping | `models/chains.py`, `models/pharmacy.py`, `routers/chains.py`, `services/provisioning.py`, `resolve_store_override*`, `resolve_chain_scope_pids` | Grant-checked helpers are core |
| Audit log | `audit_logs` table, `AuditLog.jsx`, `_record_audit` in `settings.py` | Helper is copied per-router — extract once |
| Facility settings | `pharmacy_settings`, Settings page | Split: generic profile vs. pharmacy-only (bill sequences, drug licence, GST) |
| Shared UI | `components/shared/*`, `components/ui/*`, Layout, SidebarNav, StoreSwitcher, `PharmaCare Design System/` | Reusable as-is; rename "PharmaCare" |
| Frontend plumbing | `lib/axios.js`, `hooks/*`, `utils/dates.js`, `utils/currency.js`, `constants/api.js`, `routes.js` | Generic |
| Excel/PDF utils | `utils/excel.py`, `bill_pdf*.py` | Excel generic; bill PDFs pharmacy |

## Pharmacy module

- Billing + bill detail + sales returns + day-end closing
- Inventory: `products`, `stock_batches`, `stock_movements`, stock transfers, reorder
- Purchases, purchase returns, suppliers
- Schedule H1 register, GST report, Reports, Dashboard
- Constants: product categories, HSN map, GST rates, dosage forms, `domainConstants.js`
- Tables: bills*, sales_return*, schedule_h1_register, day_end_closings, products, stock_*, purchases*, purchase_*, suppliers

## Shared-candidates (decide before EMR)

| Today | Becomes | Why |
|-------|---------|-----|
| `customers` | Core **Patient** | EMR needs the same person; pharmacy links to it |
| `doctors` | Core **Practitioner** | EMR encounters + pharmacy prescriber |
| `suppliers` | Pharmacy (or later Inventory module) | Procurement only |

## Blockers to a clean split

1. **`pharmacy_id` is the tenant key everywhere** — ~700 references across routers, incl. core tables (users, roles, audit_logs, user_store_roles). Needs a neutral name (e.g. `facility_id`) or a tenant abstraction.
2. **No module boundary in code** — one flat `routers/` and `models/`; `main.py` registers everything unconditionally.
3. **Permissions, roles, settings, audit are pharmacy-flavoured** — core cannot ship without them being generic.
4. **Billing and reports are huge files** (`reports.py` 2042, `billing.py` 1567 lines) mixing pharmacy rules — extract after the boundary exists.
5. **CLAUDE.md rules are PharmaCare-specific** (paise, H1, design guard) — need core vs. module rule split.

## Proposed order (needs approval)

1. Decide tenant naming (blocker 1) — one-line plain-language options to Abinash.
2. Create `core/` and `modules/pharmacy/` folders; move files, no logic changes.
3. Module registration: each module declares routers, permissions, nav items.
4. Promote customers/doctors to core Patient/Practitioner.
5. Start EMR module on top.
