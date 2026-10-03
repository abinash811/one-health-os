# PharmaCare — Database
# Version: 1.20 | Last updated: October 3, 2026
# Type: Reference
# Audience: Claude, all developers
# Rule: All schema changes go through Alembic migrations. Never ALTER TABLE manually.
#        Never hard DELETE from any table. Soft deletes only.

---

## DATABASE OVERVIEW

**Engine:** PostgreSQL 14+
**ORM:** SQLAlchemy 2.0 async
**Migrations:** Alembic
**Driver:** asyncpg

**Total tables: 24** — corrected Sep 18, 2026 (was 23, missing `day_end_closings`)

| Domain | Tables |
|--------|--------|
| Pharmacy | `pharmacies`, `pharmacy_settings` |
| Users | `users`, `roles`, `audit_logs`, `password_reset_tokens` |
| Products | `products`, `stock_batches`, `stock_movements` |
| Billing | `bills`, `bill_items`, `bill_payment_splits`, `sales_returns`, `sales_return_items`, `schedule_h1_register`, `day_end_closings` |
| Purchases | `purchases`, `purchase_items`, `purchase_payments`, `purchase_returns`, `purchase_return_items` |
| Customers | `customers`, `doctors` |
| Suppliers | `suppliers` |

---

## CORE RULES

```
1. Every table with pharmacy data has pharmacy_id — multi-tenancy
2. All money columns end in _paise — integer, never float
3. Soft delete: deleted_at timestamp, never DELETE FROM
4. All PKs are UUID — never integer IDs
5. created_at + updated_at on every mutable table
6. Every FK column has an index
```

---

## ENTITY RELATIONSHIP

```
pharmacies
  ├── pharmacy_settings (1:1)
  ├── users (1:many) → roles
  ├── audit_logs (1:many)
  ├── products (1:many)
  │     └── stock_batches (1:many)
  │           └── stock_movements (1:many)
  ├── bills (1:many)
  │     ├── bill_items (1:many) → products, stock_batches
  │     └── schedule_h1_register (1:many) → products
  ├── sales_returns (1:many) → bills
  │     └── sales_return_items (1:many) → products, stock_batches
  ├── purchases (1:many) → suppliers
  │     ├── purchase_items (1:many) → products, stock_batches
  │     └── purchase_payments (1:many)
  ├── purchase_returns (1:many) → purchases, suppliers
  │     └── purchase_return_items (1:many) → products, stock_batches
  ├── customers (1:many)
  ├── doctors (1:many)
  └── suppliers (1:many)
```

---

## TABLE REFERENCE

---

### `pharmacies`
The root entity. Every piece of data belongs to a pharmacy.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `name` | String(200) | Pharmacy display name |
| `address` | Text | Full address |
| `city` | String(100) | — |
| `state` | String(100) | Indian state |
| `pincode` | String(6) | 6-digit Indian PIN code |
| `phone` | String(10) | 10-digit mobile |
| `email` | String(200) | Optional |
| `gstin` | String(15) | GST Identification Number |
| `drug_license_number` | String(50) | Required to operate legally |
| `drug_license_expiry` | Date | Future: renewal alert |
| `fssai_number` | String(20) | Food Safety license if applicable |
| `pan_number` | String(10) | PAN for IT filings |
| `logo_url` | Text | Logo image URL — used on printed/digital bills |
| `chain_id` | UUID FK → `chains.id`, nullable | `NULL` = standalone single-store pharmacy (every pharmacy today). Added `3bc60ce0ce95` for Phase 2 multi-chain (`docs/26_MULTI_CHAIN_SCOPE.md`) — not read by any login/permission code yet. |
| `is_active` | Boolean | Soft disable |
| `created_at`, `updated_at` | TIMESTAMP | — |

---

### `chains` — added `3bc60ce0ce95`, Sep 26, 2026, Phase 2 groundwork only

Groups several already-independent `pharmacies` rows under one HQ account.
Nothing reads this table yet — see `docs/26_MULTI_CHAIN_SCOPE.md`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `name` | String(200) | Chain/HQ display name |
| `owner_user_id` | UUID FK → `users.id`, nullable | — |
| `is_active` | Boolean | — |
| `created_at`, `updated_at` | TIMESTAMP | — |

---

### `user_store_roles` — added `3bc60ce0ce95`, Sep 26, 2026, Phase 2 groundwork only

One row per (person, store) they can access, with their role at that
store. `UNIQUE(user_id, pharmacy_id)`. Kept correct going forward by
`services/provisioning.sync_user_store_role()`, called everywhere a
`User` row is created — not read by login/permission checks yet, which
still use `users.pharmacy_id`/`role_id` directly. For today's
single-store reality this is exactly one row per user.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `user_id` | UUID FK → `users.id`, `ON DELETE CASCADE` | — |
| `pharmacy_id` | UUID FK → `pharmacies.id` | — |
| `role_id` | UUID FK → `roles.id` | — |
| `created_at`, `updated_at` | TIMESTAMP | — |

---

### `stock_transfers` — added `e3511cb2db2b`, Sep 26, 2026, Phase 2 Step 5

Header row for one cross-store stock transfer. Instant (v1 — no
in-transit holding state). `is_cross_gstin` classifies whether the two
stores' GSTINs differ (real "supply" under GST, needs a tax invoice) or
match/are blank (just an internal move, delivery challan) — display
only, this table never triggers an actual document generation.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `transfer_number` | String(50) | `TRF-{year}-{6 hex}`, `UNIQUE(source_pharmacy_id, transfer_number)` |
| `source_pharmacy_id` | UUID FK → `pharmacies.id` | — |
| `destination_pharmacy_id` | UUID FK → `pharmacies.id` | — |
| `transfer_date` | Date | Defaults to today |
| `is_cross_gstin` | Boolean | See above |
| `source_gstin`, `destination_gstin` | String(15), nullable | Snapshot at transfer time |
| `notes` | Text, nullable | — |
| `initiated_by` | UUID FK → `users.id` | — |
| `reversed_at` | TIMESTAMP, nullable | Set by `POST /stock-transfers/{id}/reverse` |
| `reversed_by` | UUID FK → `users.id`, nullable | — |
| `created_at` | TIMESTAMP | — |

---

### `stock_transfer_items` — added `e3511cb2db2b`, Sep 26, 2026, Phase 2 Step 5

One row per medicine/batch moved in a transfer. Batch number, expiry,
cost, and MRP are snapshotted from the source batch at transfer time —
preserved exactly at the destination, never re-derived.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `transfer_id` | UUID FK → `stock_transfers.id`, `ON DELETE CASCADE` | — |
| `product_sku`, `product_name`, `batch_number` | String | Snapshot, not a live join |
| `expiry_date` | Date | — |
| `quantity` | Integer | — |
| `cost_price_paise`, `mrp_paise` | Integer | — |
| `source_batch_id`, `destination_batch_id` | UUID FK → `stock_batches.id` | Used by the reversal check |
| `created_at` | TIMESTAMP | — |

---

### `pharmacy_settings`
One row per pharmacy (`UNIQUE` on `pharmacy_id`). Configurable defaults, grouped
by the same headings used as comments in `backend/models/pharmacy.py` —
keep this table and those comments in sync when either changes.

**Bill sequence — Sales Invoice**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `bill_prefix` | String(10) | `"INV"` | Prefix for bill numbers |
| `bill_sequence_number` | Integer | `1` | Next bill number to use |
| `bill_number_length` | Integer | `6` | Zero-padding length |

**Bill sequence — Sales Return (credit note)**
Separate gapless series from the Invoice sequence above — GST requires each
to be its own series.

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `return_prefix` | String(10) | `"CN"` | Prefix for return/credit-note numbers |
| `return_sequence_number` | Integer | `1` | Next return number to use |
| `return_number_length` | Integer | `5` | Zero-padding length |

**Inventory**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `low_stock_threshold_days` | Integer | `30` | **Misnamed** (not a day count — renaming is a separate migration, tracked as tech debt). Currently unused as an alert threshold anywhere — fixed August 22, 2026 to stop being read as one at all, since despite the name it was always applied as a raw unit-quantity, not real "days of stock remaining" (nothing computes sales velocity). Every low-stock screen now uses each product's own `reorder_level` instead (see `docs/15_ROADMAP.md` RULE MISSES LOG). |
| `near_expiry_threshold_days` | Integer | `90` | Alert when expiry < N days away |
| `block_expired_stock` | Boolean | `true` | **Added August 22, 2026** (migration `d81f3b0c6a4e`). Enforced in `billing.py` create_bill/update_bill — blocks finalizing a sale on an expired batch. |
| `allow_near_expiry_sale` | Boolean | `true` | **Added August 22, 2026** (migration `d81f3b0c6a4e`). Enforced the same way — `false` blocks finalizing a sale on a near-expiry batch. No warning UI yet when `true` (default). |

**Notifications**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `alert_low_stock_enabled` | Boolean | `true` | — |
| `alert_near_expiry_enabled` | Boolean | `true` | — |
| `alert_drug_license_enabled` | Boolean | `true` | — |
| `drug_license_alert_days` | Integer | `90` | Alert when license expiry < N days away |

**GST**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `default_gst_rate` | Numeric(5,2) | `5.00` | Default GST rate for new products |
| `is_composition_scheme` | Boolean | `false` | **Unused as of Sep 12, 2026** — column still exists (no migration to drop it, harmless) but its Settings UI toggle and read/write API wiring were removed since nothing ever consumed the value; see `docs/24_REPORTS_ACCEPTANCE_SPEC.md` GST11 |
| `default_hsn_medicines` | String(10) | `"3004"` | Default HSN code for medicine products |
| `default_hsn_surgical` | String(10) | `"9018"` | Default HSN code for surgical/non-medicine products |
| `auto_apply_hsn` | Boolean | `true` | Auto-fill HSN from category on product create |
| `gst_type` | String(20) | `"intrastate"` | `intrastate` (CGST+SGST) or `interstate` (IGST) |
| `round_off_amount` | Boolean | `true` | Round grand total to nearest rupee |
| `print_gst_summary` | Boolean | `true` | Show GST breakup on printed bill |

**Print**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `paper_size` | String(10) | `"80mm"` | Thermal `80mm`/`58mm` or `A4`/`A5` |
| `print_logo` | Boolean | `true` | Show logo on printed bill |
| `print_drug_license` | Boolean | `true` | Show drug license number on bill |
| `print_patient_name` | Boolean | `true` | — |
| `print_gstin` | Boolean | `true` | — |
| `print_fssai` | Boolean | `false` | — |
| `print_signature` | Boolean | `false` | Show signature line |
| `print_pan` | Boolean | `false` | — |
| `bill_header` | Text | `null` | Custom header text |
| `bill_footer` | Text | `"Thank you for your purchase!"` | Custom footer text |

**Digital receipt** (shareable, screen-viewed — always A4-style, no paper
size choice; "Show on Bill" toggles above and the item table are shared
with Print, both formats show the same billing information)

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `digital_use_default_header` | Boolean | `true` | `false` = use custom header image below |
| `digital_header_image_url` | Text | `null` | Custom header image |
| `digital_footer_image_url` | Text | `null` | Custom footer image |
| `digital_header_height_px` | Integer | `100` | — |
| `digital_footer_height_px` | Integer | `60` | — |
| `digital_bill_header` | Text | `null` | Custom header text (digital only) |
| `digital_bill_footer` | Text | `null` | Custom footer text (digital only) |

---

### `roles`
RBAC roles. System roles are seeded on startup, custom roles can be created.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | Scoped per pharmacy |
| `name` | String(100) | UNIQUE per pharmacy |
| `description` | Text | — |
| `is_system_role` | Boolean | `true` = seeded, cannot delete |
| `permissions` | JSONB | Permission flags per module |
| `is_active` | Boolean | — |

**Default system roles:** `admin`, `manager`, `cashier`, `inventory_staff` (`backend/constants.py::DEFAULT_ROLES` — full permission list per role documented in `docs/14_SECURITY.md`)

---

### `users`
Pharmacy staff members. One user belongs to one pharmacy and one role.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `role_id` | UUID FK → roles | — |
| `name` | String(200) | — |
| `email` | String(200) | UNIQUE per pharmacy |
| `phone` | String(10) | Optional |
| `password_hash` | String(255) | bcrypt hash — never store plain text |
| `is_active` | Boolean | Inactive = cannot login |
| `is_admin` | Boolean, default `false` | Administrator checkbox (migration `a7d3e91c4b20`, Oct 3, 2026) — separate from the clinical role, so one person can be a Doctor AND an admin. Admin = every permission + manage team/roles/settings. Backfilled `true` for everyone in the `admin` role. |
| `last_login_at` | TIMESTAMP | — |

---

### `password_reset_tokens`
Self-service "Forgot password" tokens (added Sep 16, 2026 —
docs/15_ROADMAP.md Auth Overhaul #6). No `pharmacy_id` column — a
locked-out user has no JWT to derive one from; the row's own `user_id` FK
is the only scope needed, and lookups always go by `token_hash`, not by id.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `user_id` | UUID FK → users, `ondelete=CASCADE` | — |
| `token_hash` | String(64) | SHA-256 hex digest of the raw token — never the raw value itself |
| `expires_at` | TIMESTAMP | 1 hour after creation |
| `used_at` | TIMESTAMP | NULL until consumed — single-use enforced by checking this is still NULL |
| `created_at` | TIMESTAMP | — |

**Indexes:** `token_hash` (unique)

---

### `audit_logs`
Immutable record of every significant action. Never delete rows from this table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `user_id` | UUID FK → users | Who did it |
| `action` | String(100) | `create`, `update`, `delete`, `payment`, `status_change` |
| `entity_type` | String(100) | `invoice`, `batch`, `product`, `purchase`, `user` |
| `entity_id` | UUID | ID of the affected record |
| `old_values` | JSONB | State before change |
| `new_values` | JSONB | State after change |
| `ip_address` | INET | Client IP |
| `created_at` | TIMESTAMP | — |

**Indexes:** `pharmacy_id`, `(entity_type, entity_id)`, `user_id`, `created_at`

---

### `products`
The product master. One row per unique medicine.

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | UUID PK | — | — |
| `pharmacy_id` | UUID FK | — | — |
| `sku` | String(100) | — | UNIQUE per pharmacy — used in URL `/inventory/product/:sku` |
| `barcode` | String(100) | Optional | EAN/UPC for scanner |
| `name` | String(300) | required | Brand name e.g. "Crocin 500mg" |
| `generic_name` | String(300) | Optional | Salt name e.g. "Paracetamol" |
| `brand` | String(200) | Optional | Manufacturer brand |
| `manufacturer` | String(200) | Optional | Who makes it |
| `category` | String(100) | Optional | e.g. "Antibiotics", "Analgesics" |
| `drug_schedule` | String(20) | `"OTC"` | `OTC`, `H`, `H1`, `X` |
| `dosage_form` | String(100) | Optional | `Tablet`, `Syrup`, `Injection`, etc. |
| `strength` | String(100) | Optional | e.g. `"500mg"`, `"10mg/5ml"`. Wired into `ProductCreate`/`ProductUpdate`, search, and the UI August 22, 2026 — was a real column with no way to set it before that. |
| `pack_size` | String(100) | Optional | e.g. `"10 tablets"`, `"100ml"` |
| `units_per_pack` | Integer | `1` | Tablets in a strip |
| `hsn_code` | String(10) | `"3004"` | Determines GST rate |
| `gst_rate` | Numeric(5,2) | `5.00` | `0`, `5`, `12`, or `18` |
| `reorder_level` | Integer | `10` | Alert threshold in packs |
| `reorder_quantity` | Integer | `100` | Default reorder quantity |
| `storage_location` | String(100) | Optional | Shelf/rack reference |
| `requires_refrigeration` | Boolean | `false` | Cold chain flag. Wired into `ProductCreate`/`ProductUpdate`, the `cold_chain_only` Inventory filter, bulk-update, and the UI August 22, 2026 — same fix as `strength` above. |
| `is_active` | Boolean | `true` | — |
| `deleted_at` | TIMESTAMP | null | Soft delete |

**Indexes:** `pharmacy_id`, `(pharmacy_id, name)`, `(pharmacy_id, barcode)`, `(pharmacy_id, generic_name)`, `(pharmacy_id, drug_schedule)`
**Constraint:** UNIQUE `(pharmacy_id, sku)`

---

### `stock_batches`
Every physical batch of a product in stock. One product has many batches.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `product_id` | UUID FK → products | — |
| `batch_number` | String(100) | As printed on box |
| `expiry_date` | Date | As printed on box (end of month) |
| `manufacture_date` | Date | Optional |
| `mrp_paise` | Integer | MRP at time of purchase |
| `cost_price_paise` | Integer | What pharmacy paid (landed cost) |
| `sale_price_paise` | Integer | Optional override (default = MRP) |
| `quantity_received` | Integer | Original qty received |
| `quantity_on_hand` | Integer | Current qty — decrements on sale |
| `quantity_sold` | Integer | Running total sold |
| `quantity_returned` | Integer | Running total returned |
| `quantity_written_off` | Integer | Expired/damaged write-offs |
| `is_active` | Boolean | `false` when qty reaches 0 |

**Rule:** `quantity_on_hand` must never go below 0.
**FEFO:** Sort by `expiry_date ASC` to sell earliest-expiring first.

**Indexes:** `product_id`, `(pharmacy_id, expiry_date)`, `(product_id, quantity_on_hand)`

---

### `stock_movements`
Immutable ledger of every stock change. Never delete rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `batch_id` | UUID FK → stock_batches | — |
| `product_id` | UUID FK → products | — |
| `movement_type` | String(50) | `purchase`, `sale`, `sales_return`, `purchase_return`, `adjustment`, `opening_stock`, `transfer_out`, `transfer_in`, `transfer_reversal` (added Sep 26, 2026, Phase 2 Step 5) |
| `quantity` | Integer | Negative for deductions, positive for additions |
| `quantity_before` | Integer | Snapshot before movement |
| `quantity_after` | Integer | Snapshot after movement |
| `reference_type` | String(50) | `bill`, `purchase`, `adjustment`, `stock_transfer` |
| `reference_id` | UUID | FK to the source record |
| `user_id` | UUID FK → users | Who triggered it |
| `notes` | Text | Optional reason |
| `created_at` | TIMESTAMP | Immutable |

---

### `bills`
Every sale transaction. Core of the system.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `bill_number` | String(50) | UNIQUE per pharmacy. Drafts: `DRAFT-{uuid}`. Settled: `INV-000042` |
| `invoice_type` | String(20) | `SALE`, `SALES_RETURN` |
| `bill_date` | Date | Date of sale |
| `bill_time` | Time (tz) | Time of sale |
| `customer_id` | UUID FK → customers | Optional |
| `customer_name` | String(200) | Snapshot — even if customer deleted |
| `customer_phone` | String(10) | Snapshot |
| `customer_gstin` | String(15) | Snapshot — for B2B bills |
| `doctor_id` | UUID FK → doctors | Required for H1 drugs |
| `doctor_name` | String(200) | Snapshot |
| `prescription_number` | String(100) | Optional |
| `prescription_date` | Date | Optional |
| `subtotal_paise` | Integer | Taxable amount before bill discount |
| `mrp_total_paise` | Integer | Sum of MRP × qty (before any discount) |
| `item_discount_paise` | Integer | Total item-level discounts |
| `bill_discount_paise` | Integer | Overall bill discount |
| `bill_discount_percent` | Numeric(5,2) | Overall bill discount as % |
| `total_discount_paise` | Integer | `item_discount + bill_discount` |
| `taxable_amount_paise` | Integer | `subtotal - bill_discount` |
| `total_cgst_paise` | Integer | CGST portion of GST |
| `total_sgst_paise` | Integer | SGST portion of GST |
| `total_igst_paise` | Integer | IGST portion of GST (interstate bills) |
| `total_gst_paise` | Integer | `cgst + sgst + igst` |
| `grand_total_paise` | Integer | Final amount payable |
| `amount_paid_paise` | Integer | Amount collected |
| `balance_paise` | Integer | `grand_total - amount_paid` |
| `payment_method` | String(20) | `cash`, `upi`, `card`, `credit`, `cheque` |
| `payment_reference` | String(100) | UPI/card/cheque reference number |
| `cost_total_paise` | Integer | Cost of goods sold |
| `margin_paise` | Integer | `grand_total - cost_total` |
| `margin_percent` | Numeric(5,2) | Margin as % of grand_total |
| `status` | String(20) | `draft`, `paid`, `due`, `partial` |
| `internal_note` | Text | Staff-only note — never printed |
| `delivery_note` | Text | Delivery instructions |
| `billed_by` | UUID FK → users | Cashier |
| `deleted_at` | TIMESTAMP | Soft delete |

**Constraint:** UNIQUE `(pharmacy_id, bill_number)`
**Indexes:** `pharmacy_id`, `(pharmacy_id, bill_date)`, `customer_id`, `(pharmacy_id, status)`, partial index on `status='paid'`, partial index on `status='due'`

---

### `bill_items`
Line items on a bill. All values are snapshots — do not join to products for display.

| Column | Type | Notes |
|--------|------|-------|
| `bill_id` | UUID FK → bills | CASCADE delete if bill deleted |
| `product_id` | UUID FK → products | For analytics only — not for display |
| `batch_id` | UUID FK → stock_batches | — |
| `product_name` | String(300) | **Snapshot** — use this for display |
| `generic_name` | String(300) | **Snapshot** |
| `batch_number` | String(100) | **Snapshot** |
| `expiry_date` | Date | **Snapshot** |
| `hsn_code` | String(10) | **Snapshot** — for GST report |
| `drug_schedule` | String(20) | **Snapshot** — for H1 register |
| `quantity` | Integer | — |
| `mrp_paise` | Integer | MRP at time of sale |
| `sale_price_paise` | Integer | Actual sale price |
| `cost_price_paise` | Integer | Cost at time of sale |
| `discount_percent` | Numeric(5,2) | — |
| `discount_paise` | Integer | — |
| `gst_rate` | Numeric(5,2) | **Snapshot** |
| `cgst_rate`, `sgst_rate`, `igst_rate` | Numeric(5,2) | intrastate: cgst+sgst = gst_rate. interstate: igst = gst_rate |
| `taxable_amount_paise` | Integer | `mrp × qty - discount` |
| `cgst_paise`, `sgst_paise`, `igst_paise` | Integer | Split GST amounts |
| `gst_paise` | Integer | Total GST for this line |
| `line_total_paise` | Integer | `taxable + gst` |
| `line_cost_paise` | Integer | `cost × qty` |

**Critical rule:** Never use `product_id` to look up product name for bill display.
Always use `product_name` (the snapshot column).

---

### `bill_payment_splits`
One leg of a "Multi" payment — a bill paid across 2+ real methods at
checkout (e.g. ₹300 cash + ₹200 UPI). Added Sep 16, 2026; only created for
a fully-paid bill split across `cash`/`upi`/`card` — "Due" is its own
separate flow, never combined with a split. No `pharmacy_id` column —
always reached via its `bill_id` FK, which is already pharmacy-scoped.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `bill_id` | UUID FK → bills, `ondelete=CASCADE` | — |
| `payment_method` | String(20) | `cash`, `upi`, or `card` — never `due`/`multiple` |
| `amount_paise` | Integer | This leg's share of the bill total |
| `created_at` | TIMESTAMP | — |

**Cross-cutting:** Day-End Closing (`reports.py _day_end_breakdown`) reads
this via the audit log's `payment_splits` snapshot, not this table
directly, to explode a Multi bill into real per-method cash-drawer
buckets — see `docs/07_BUSINESS_LOGIC.md`'s Multi payment section.

---

### `sales_returns`
A return against an existing bill (credit note). One bill can have multiple
partial returns.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `original_bill_id` | UUID FK → bills | The bill being returned against |
| `return_number` | String(50) | UNIQUE per pharmacy — uses `return_prefix`/`return_sequence_number` from `pharmacy_settings` |
| `return_date` | Date | — |
| `return_reason` | Text | Optional |
| `total_paise` | Integer | Sum of returned line amounts before GST |
| `total_gst_paise` | Integer | GST reversed |
| `grand_total_paise` | Integer | Total refund amount |
| `refund_method` | String(20) | `cash`, `upi`, `store_credit`, etc. |
| `status` | String(20) | `pending`, `completed` |
| `notes` | Text | Optional |
| `created_by` | UUID FK → users | — |

**Constraint:** UNIQUE `(pharmacy_id, return_number)`

---

### `sales_return_items`
Line items on a sales return. All values are snapshots, same rule as `bill_items`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `sales_return_id` | UUID FK → sales_returns | CASCADE delete if return deleted |
| `bill_item_id` | UUID FK → bill_items | The original line being returned |
| `product_id` | UUID FK → products | For analytics only |
| `batch_id` | UUID FK → stock_batches | Batch stock is returned to |
| `product_name` | String(300) | **Snapshot** |
| `batch_number` | String(100) | **Snapshot** |
| `quantity` | Integer | Quantity returned |
| `sale_price_paise` | Integer | Snapshot from original sale |
| `gst_rate` | Numeric(5,2) | **Snapshot** |
| `gst_paise` | Integer | GST reversed for this line |
| `line_total_paise` | Integer | — |
| `return_to_stock` | Boolean | `true` = adds back to `stock_batches.quantity_on_hand`, `false` = written off (damaged) |

---

### `schedule_h1_register`
Legal compliance register. Every H1 drug sale creates a row here.

| Column | Type | Notes |
|--------|------|-------|
| `pharmacy_id` | UUID FK → pharmacies | — |
| `bill_id` | UUID FK → bills | Source bill |
| `product_name` | String(300) | Snapshot |
| `batch_number` | String(100) | Snapshot |
| `quantity` | Integer | — |
| `prescriber_name` | String(200) | Doctor name — required |
| `prescriber_registration_number` | String(100), nullable | Optional but important |
| `prescriber_address` | Text, nullable | Added here Sep 19, 2026, was missing from this doc — populated from the matched `Doctor` record, blank if the doctor name doesn't match one |
| `patient_name` | String(200) | Patient name — required |
| `patient_address` | Text, nullable | Added here Sep 19, 2026, was missing from this doc — required at billing time (Schedule H1 Rule 65, `docs/07_BUSINESS_LOGIC.md` FLOW 6), not optional despite the nullable column |
| `patient_age` | Integer, nullable | Added here Sep 19, 2026, was missing from this doc — optional, no billing-time check requires it |
| `supply_date` | Date | Date dispensed |
| `dispensed_by` | UUID FK → users | Pharmacist who dispensed |

**Never delete rows from this table.** Drug inspector can audit at any time.

---

### `day_end_closings`
Added Sep 18, 2026 — this table existed since Sep 15, 2026 (the Day-End
Closing feature) but was missing from this doc entirely; found while
checking the real table count against `backend/models/`. One row per
pharmacy per calendar day: the cash a cashier physically counted vs.
what the system expected from that day's real cash-method bills.

| Column | Type | Notes |
|--------|------|-------|
| `pharmacy_id` | UUID FK → pharmacies | — |
| `closing_date` | Date | Unique with `pharmacy_id` — one closing per pharmacy per day |
| `expected_cash_paise` | Integer | Computed from that day's real cash bills |
| `counted_cash_paise` | Integer | What the cashier physically counted |
| `variance_paise` | Integer | `counted - expected` — persisted, not recomputed on read |
| `notes` | Text, nullable | — |
| `closed_by` | UUID FK → users | Who ran the close |
| `closed_at` | Timestamptz | — |

---

### `purchases`
Stock purchase from a supplier.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `supplier_id` | UUID FK → suppliers | — |
| `purchase_number` | String(50) | UNIQUE per pharmacy |
| `supplier_invoice_number` | String(100) | Supplier's invoice ref |
| `supplier_invoice_date` | Date | Date on supplier's invoice |
| `purchase_date` | Date | — |
| `grn_number` | String(50) | Goods Receipt Note number |
| `received_date` | Date | Date goods were physically received |
| `subtotal_paise` | Integer | — |
| `total_discount_paise` | Integer | Trade discount total |
| `total_gst_paise` | Integer | ITC-eligible GST — `cgst + sgst + igst` |
| `total_cgst_paise` | Integer | CGST portion (intrastate) |
| `total_sgst_paise` | Integer | SGST portion (intrastate) |
| `total_igst_paise` | Integer | IGST portion (interstate) |
| `grand_total_paise` | Integer | Payable to supplier |
| `amount_paid_paise` | Integer | Amount paid so far — sum of `purchase_payments` |
| `status` | String(20) | `draft`, `confirmed` |
| `payment_status` | String(20) | `unpaid`, `partial`, `paid` |
| `due_date` | Date | Payment due date |
| `notes` | Text | Optional |
| `created_by` | UUID FK → users | — |
| `deleted_at` | TIMESTAMP | Soft delete |

---

### `purchase_items`
Line items on a purchase. Creates stock_batches when purchase is confirmed.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `purchase_id` | UUID FK → purchases | CASCADE delete if purchase deleted |
| `product_id` | UUID FK → products | — |
| `batch_id` | UUID FK → stock_batches | Set when purchase confirmed |
| `product_name` | String(300) | Snapshot |
| `batch_number` | String(100) | As on supplier invoice |
| `expiry_date` | Date | As on supplier invoice |
| `hsn_code` | String(10) | Snapshot — for GST report |
| `quantity_ordered` | Integer | — |
| `quantity_received` | Integer | May differ from ordered |
| `units_per_pack` | Integer | Tablets/units in a strip/pack |
| `mrp_paise` | Integer | MRP on this batch |
| `cost_price_paise` | Integer | PTR after discount |
| `discount_percent` | Numeric(5,2) | Trade discount |
| `gst_rate` | Numeric(5,2) | GST rate for ITC |
| `cgst_rate`, `sgst_rate`, `igst_rate` | Numeric(5,2) | intrastate: cgst+sgst = gst_rate. interstate: igst = gst_rate |
| `taxable_amount_paise` | Integer | `cost_price × qty - discount` |
| `gst_amount_paise` | Integer | Total GST for this line |
| `line_total_paise` | Integer | `taxable + gst` |

---

### `purchase_payments`
Payments made against a purchase. A purchase can be paid in multiple
installments — `purchases.amount_paid_paise` is the sum of these rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `purchase_id` | UUID FK → purchases | — |
| `amount_paise` | Integer | — |
| `payment_method` | String(20) | `cash`, `upi`, `card`, `cheque`, `bank_transfer` |
| `payment_date` | Date | — |
| `reference_number` | String(100) | UPI/cheque/bank reference |
| `notes` | Text | Optional |
| `created_by` | UUID FK → users | — |

---

### `purchase_returns`
A return of stock to a supplier (debit note) — the purchase-side mirror of
`sales_returns`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `pharmacy_id` | UUID FK | — |
| `purchase_id` | UUID FK → purchases | The purchase being returned against |
| `supplier_id` | UUID FK → suppliers | — |
| `return_number` | String(50) | UNIQUE per pharmacy |
| `return_date` | Date | — |
| `return_reason` | String(50) | Required — e.g. `expired`, `damaged`, `wrong_item` |
| `subtotal_paise` | Integer | — |
| `total_gst_paise` | Integer | GST reversed |
| `grand_total_paise` | Integer | Total credit expected from supplier |
| `status` | String(20) | `pending`, `completed` |
| `credit_note_number` | String(100) | Supplier's credit note ref, once received |
| `notes` | Text | Optional |
| `created_by` | UUID FK → users | — |

**Constraint:** UNIQUE `(pharmacy_id, return_number)`

---

### `purchase_return_items`
Line items on a purchase return.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `purchase_return_id` | UUID FK → purchase_returns | CASCADE delete if return deleted |
| `product_id` | UUID FK → products | — |
| `batch_id` | UUID FK → stock_batches | Batch stock is deducted from |
| `product_name` | String(300) | Snapshot |
| `batch_number` | String(100) | Snapshot |
| `expiry_date` | Date | Snapshot |
| `quantity` | Integer | Quantity returned to supplier |
| `cost_price_paise` | Integer | Snapshot from original purchase |
| `gst_rate` | Numeric(5,2) | Snapshot |
| `gst_amount_paise` | Integer | GST reversed for this line |
| `line_total_paise` | Integer | — |

---

### `customers`

| Column | Type | Notes |
|--------|------|-------|
| `name` | String(200) | — |
| `phone` | String(10) | Primary identifier for walk-in customers |
| `alternate_phone` | String(10) | Optional |
| `email` | String(200) | Optional |
| `age` | Integer | Optional |
| `gender` | String(10) | Optional |
| `address` | Text | Optional |
| `city` | String(100) | Optional |
| `notes` | Text | Optional — added Sep 12, 2026, `routers/customers.py`'s `CustomerCreate`/update + `CustomerFormDialog.jsx`'s `<Textarea>` |
| `customer_type` | String(20) | `retail`, `wholesale`, `institution` — default `retail` |
| `gstin` | String(15) | For B2B customers |
| `credit_days` | Integer | Payment terms — default `0` (unused; no code path reads it) |
| `is_active` | Boolean | — |
| `deleted_at` | TIMESTAMP | Soft delete |

**No stored `outstanding_paise` column** — removed Sep 12, 2026 (migration
`bcd3c6cd10e2`). It was never written to, always showing ₹0. The API's
`outstanding` field is now computed fresh on every read
(`_outstanding_paise_by_customer()`, `routers/customers.py`) as the sum of
`Bill.balance_paise` for that customer's real `'due'` bills — same safe
pattern as `get_customer_stats`, can't drift.

**Indexes:** `pharmacy_id`, `(pharmacy_id, phone)`, `(pharmacy_id, name)`

---

### `doctors`
Prescribing doctors. Required for Schedule H1 billing.

| Column | Type | Notes |
|--------|------|-------|
| `name` | String(200) | — |
| `qualification` | String(200) | e.g. "MBBS, MD" |
| `registration_number` | String(100) | Medical Council reg number |
| `specialization` | String(200) | e.g. "General Physician" |
| `hospital` | String(200) | — |
| `phone` | String(10) | — |
| `address` | Text | Optional |
| `is_active` | Boolean | — |
| `deleted_at` | TIMESTAMP | Soft delete |

**Indexes:** `pharmacy_id`, `(pharmacy_id, name)`

---

### `suppliers`

| Column | Type | Notes |
|--------|------|-------|
| `name` | String(200) | Distributor/stockist name |
| `contact_person` | String(200) | Optional |
| `phone` | String(10) | Optional |
| `alternate_phone` | String(10) | Optional |
| `email` | String(200) | Optional |
| `address` | Text | Optional |
| `city` | String(100) | Optional |
| `state` | String(100) | Optional |
| `pincode` | String(6) | Optional |
| `gstin` | String(15) | For ITC reconciliation |
| `drug_license_number` | String(50) | Supplier's drug license |
| `pan_number` | String(10) | Optional |
| `credit_days` | Integer | Default 30 — payment terms |
| `credit_limit_paise` | Integer | Optional credit limit |
| `is_active` | Boolean | — |
| `deleted_at` | TIMESTAMP | Soft delete |

**Indexes:** `pharmacy_id`

---

## EMR MODULE TABLES (added Oct 2, 2026 — migration `ecd85336d185`)

> EMR is module #2 (`docs/28_EMR_SCOPE.md`). Models live in `backend/modules/emr/models.py`,
> not `backend/models/`. These tables never reference pharmacy-module tables, so EMR runs
> with the pharmacy module off. `pharmacy_id` is still the tenant key.

### `emr_patients`
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `pharmacy_id` | UUID FK → pharmacies | Tenant key |
| `name` | String(200) | Required |
| `phone`, `alternate_phone` | String(10) | Not unique — families share a phone |
| `email` | String(200) | |
| `date_of_birth` / `age` | Date / Integer | Either may be filled |
| `gender`, `blood_group` | String | |
| `address`, `city` | Text / String | |
| `allergies`, `notes` | Text | |
| `source` | String(20) | `emr` or `pharmacy` — drives the "Added in …" badge |
| `customer_id` | UUID, **no FK** | Optional soft link to `customers.id`, matched by phone, only when both modules are on |
| `is_active`, `deleted_at`, `created_at`, `updated_at` | | Soft delete |

Indexes: pharmacy; (pharmacy, phone); (pharmacy, name); customer_id.

### `emr_doctor_schedules`
- One working-hours block per row: `doctor_user_id` (FK → users), `weekday` (Mon=0..Sun=6), `start_time`, `end_time`, `slot_minutes` (default 15).
- A doctor with morning + evening clinic has two rows for the same weekday.
- A doctor is a `users` row, not the pharmacy-module `doctors` directory.

### `emr_appointments`
| Column | Type | Notes |
|--------|------|-------|
| `patient_id` | UUID FK → emr_patients | |
| `doctor_user_id` | UUID FK → users | |
| `appointment_date` | Date | |
| `start_time`, `end_time` | Time, nullable | NULL start_time = walk-in (token only) |
| `token_number` | Integer | Per doctor per day |
| `appointment_type` | String | `scheduled` / `walk_in` |
| `status` | String | `booked → checked_in → in_consult → completed`, or `cancelled` / `no_show` |
| `reason`, `cancel_reason` | Text | |
| `checked_in_at`, `started_at`, `completed_at` | Timestamp | |
| `created_by` | UUID FK → users | |

Constraints: unique (pharmacy, doctor, date, token); partial unique (pharmacy, doctor, date, start_time) for live bookings only (not cancelled / no-show / deleted) — blocks double-booking.
Status/type values: `backend/modules/emr/constants.py`.

### `emr_settings` (migration `3c734b0950bb`)
One row per clinic, created with defaults on first read (`modules/emr/settings_service.py`).
| Column | Type | Notes |
|--------|------|-------|
| `pharmacy_id` | UUID FK, **unique** | |
| `clinic_name`, `clinic_address`, `clinic_phone`, `clinic_email`, `registration_no`, `rx_footer` | text, nullable | Printed on prescriptions; blank name/address/phone fall back to the pharmacy record |
| `rx_prefix` | String(10) | Default `RX-` |
| `uhid_prefix`, `uhid_digits` | String(10), Integer | Default `UH-` / 6 |
| `uhid_next` | Integer | Next number to issue; advanced atomically (`UPDATE ... RETURNING`), never hand-edited, never reused |
| `default_slot_minutes` | Integer | Default 15 |
| `patient_form` | JSONB | `{field: hidden\|optional\|required}`; missing keys use `PATIENT_FORM_DEFAULTS`. `name` is not configurable |

### `emr_doctor_profiles`
| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID FK → users | Unique per pharmacy |
| `specialty`, `qualification`, `registration_no` | String, nullable | Printed under the doctor's name on their Rx |

`emr_patients.uhid` (String(30), nullable) — the clinic's own patient ID; partial unique index per pharmacy. The migration backfilled existing patients as `UH-000001…` (oldest first).

`emr_doctor_profiles.consultation_fee_paise` (Integer, nullable; migration `1462660fbf8c`) — default fee posted to the patient's account at check-in; blank or 0 = no fee.

### `practitioners` (added Oct 3, 2026 — migration `d4a1f6b8c203`, docs/31_CORE_DOCTOR_SCOPE.md)
Doctors as their own records, separate from logins. Owned by the hospital, mapped to clinics via `practitioner_clinics`.
| Column | Type | Notes |
|--------|------|-------|
| `chain_id` | UUID FK → chains, nullable | NULL for a standalone clinic. Informational — visibility is decided from the caller's real store grants (`resolve_chain_scope_pids`), never a raw chain filter |
| `pharmacy_id` | UUID FK | The clinic it was created at |
| `name` | String(200) | Required |
| `specialty`, `qualification`, `registration_no`, `phone`, `email`, `hospital`, `notes` | text, nullable | Printed on prescriptions (specialty, qualification, registration) |
| `is_external` | Boolean, default false | Referring / visiting doctor not on staff |
| `user_id` | UUID FK → users, nullable | Optional login link; partial unique index — one live profile per login |
| `is_active`, `deleted_at` | Boolean / TIMESTAMP | Soft delete only |

### `practitioner_clinics`
| Column | Type | Notes |
|--------|------|-------|
| `practitioner_id`, `pharmacy_id` | UUID FKs | Unique together — which clinic a doctor practises at |
| `consultation_fee_paise` | Integer, nullable | Fee at THIS clinic (integer paise); blank/0 = no fee |
| `is_active`, `deleted_at` | | Un-mapping soft-deletes; re-adding revives the row |

Migration `e5b2c9a7d314` backfilled missing `user_store_roles` rows (logins created by `seed_admin.py` had none).

## PATIENT BILLING MODULE TABLES (added Oct 2, 2026 — migration `23cabc12aa4a`)

> Plan: `docs/29_BILLING_SCOPE.md`. Models: `backend/modules/patient_billing/models.py`. These tables have **no
> foreign keys into EMR or pharmacy tables** — the patient is a plain `patient_id` plus a name/UHID snapshot taken when the
> charge is posted. Money is integer paise; soft delete via `deleted_at`.

### `pb_charge_items`
| Column | Type | Notes |
|--------|------|-------|
| `patient_id`, `patient_name`, `patient_uhid` | UUID, String | Snapshot — no FK |
| `source_module` | String | `emr` / `lab` / `ipd` / `manual` / `pharmacy` (pharmacy not postable yet; never invoiced here) |
| `source_ref`, `encounter_ref`, `encounter_type` | String | What produced it (e.g. appointment id) — lets IPD group by admission later |
| `description`, `quantity`, `unit_price_paise`, `total_paise` | | |
| `status` | String | `unbilled → invoiced → paid`, or `void` |
| `invoice_id` | UUID FK → pb_invoices | Null while unbilled |
| `idempotency_key` | String | Unique per pharmacy (partial index) — a retried post never double-charges; never reused |
| `void_reason` | Text | |

### `pb_invoices`
| Column | Type | Notes |
|--------|------|-------|
| `invoice_number` | String | `INV-000001`, unique per pharmacy, never reused (cancelled numbers stay used) |
| `counter` | String | `front_desk` / `billing_desk` / `lab` / `ipd` — which desk issued it (day closing) |
| `status` | String | `issued → part_paid → paid`, or `cancelled` |
| `gross_paise`, `discount_paise`, `net_paise`, `paid_paise` | Integer | |
| `lines` | JSONB | Frozen copy of the charges at invoice time |
| `cancel_reason` | Text | |

### `pb_payments`
| Column | Type | Notes |
|--------|------|-------|
| `invoice_id` | UUID FK → pb_invoices | |
| `amount_paise`, `mode` (`cash`/`upi`/`card`), `reference` | | |
| `receipt_number` | String | `RCT-000001`, unique per pharmacy, never reused |
| `paid_on` | Date | Clinic's local day — used for day closing |

### `emr_prescriptions` (migration `dc6a0865f1a9`)
One row per visit — holds the WHOLE consultation record. There is deliberately no separate
consultation table (Abinash, Oct 2, 2026: "all these details should be part of one single prescription").
| Column | Type | Notes |
|--------|------|-------|
| `appointment_id` | UUID FK → emr_appointments | One live (non-cancelled) Rx per appointment — partial unique index |
| `patient_id` | UUID FK → emr_patients | |
| `doctor_user_id` | UUID FK → users | |
| `rx_number` | String(30) | `RX-000001`, unique per pharmacy |
| `status` | String | `draft` (editable) → `issued` (locked, printable) or `cancelled` |
| `vitals` | JSONB, nullable | Optional keys: `bp_systolic`, `bp_diastolic`, `pulse`, `temperature_c`, `spo2`, `weight_kg` |
| `complaints`, `diagnosis`, `advice` | Text | |
| `follow_up_date` | Date | |
| `issued_at` | Timestamp | |
| `cancel_reason` | Text | Required when cancelling |
| `created_by`, `deleted_at`, `created_at`, `updated_at` | | Soft delete |

### `emr_prescription_items`
| Column | Type | Notes |
|--------|------|-------|
| `prescription_id` | UUID FK → emr_prescriptions | ON DELETE CASCADE (lines are replaced wholesale on each draft save) |
| `sort_order` | Integer | |
| `medicine_name` | String(300) | Free text — EMR works without the pharmacy module |
| `dosage`, `frequency`, `instructions` | String | |
| `duration_days`, `quantity` | Integer, nullable | |
Index on (pharmacy_id, medicine_name) powers the clinic's own-history autocomplete.

---

## INDEXES SUMMARY

Indexes are defined in `__table_args__` in each model. Key patterns:

```python
# Every pharmacy-scoped table
Index("idx_table_pharmacy", "pharmacy_id")

# Date-range queries (reports)
Index("idx_bills_date", "pharmacy_id", "bill_date")

# Status filters
Index("idx_bills_status", "pharmacy_id", "status")

# Partial indexes (PostgreSQL) — only index rows matching condition
Index("idx_bills_paid", "pharmacy_id", "bill_date",
      postgresql_where=text("status = 'paid'"))

# Text search
Index("idx_products_name", "pharmacy_id", "name")
```

---

## MIGRATIONS

All schema changes must go through Alembic. Never ALTER TABLE manually.

```bash
# 1. Make changes to the model in backend/models/
# 2. Generate migration
cd backend
alembic revision --autogenerate -m "add barcode_verified to stock_batches"

# 3. Review the generated file in backend/migrations/versions/
# 4. Apply
alembic upgrade head

# Check current version
alembic current

# Rollback one migration
alembic downgrade -1

# See migration history
alembic history
```

**Rules:**
- Migration file names must be descriptive: `add_reorder_level_to_products` not `update_123`
- Always review auto-generated migrations — SQLAlchemy doesn't always get it right
- Never edit an applied migration — create a new one
- Migration files are committed to git alongside model changes

---

## ADDING A NEW TABLE

Checklist when adding a new model:

```
- [ ] UUID primary key (never integer)
- [ ] pharmacy_id FK + index (if pharmacy-scoped data)
- [ ] created_at with server_default=func.now()
- [ ] updated_at with server_default=func.now(), onupdate=func.now()
- [ ] deleted_at TIMESTAMP nullable (for soft delete)
- [ ] All money columns end in _paise, type Integer
- [ ] Alembic migration created and reviewed
- [ ] Model imported in backend/models/__init__.py if applicable
```

---

*Owner: Developer who makes a schema change updates this file in the same PR.*
