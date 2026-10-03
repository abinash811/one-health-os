# PharmaCare — API Reference
# Version: 1.34 | Last updated: October 3, 2026
# Type: Reference
# Audience: Claude, all developers
# Base URL: http://localhost:8000/api (dev) | https://api.pharmacare.in/api (prod)
# Auth: Bearer JWT token in Authorization header (handled by axios instance automatically)
# Rule: All new endpoints are documented here in the same PR.

---

## HOW TO CALL THE API (Frontend)

```jsx
import api from '@/lib/axios';

// GET with query params
const { data } = await api.get('/bills', { params: { page: 1, page_size: 20 } });

// POST
const { data } = await api.post('/bills', payload);

// PUT
const { data } = await api.put(`/bills/${id}`, payload);

// DELETE (soft — sets is_deleted=true on backend)
await api.delete(`/products/${id}`);
```

The axios instance automatically:
- Attaches `Authorization: Bearer {token}` from localStorage
- Redirects to `/` on 401
- Normalises error messages — catch with `error.message`

---

## RESPONSE CONVENTIONS

### Success
```json
// Single object
{ "id": "uuid", "bill_number": "INV-000042", ... }

// List with pagination
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 98,
    "total_pages": 5,
    "has_next": true,
    "has_prev": false
  }
}
```

### Error
```json
// FastAPI validation error (422)
{ "detail": [{ "loc": ["body", "field"], "msg": "field required", "type": "value_error" }] }

// Application error (400, 404, etc.)
{ "detail": "Insufficient stock in batch BN240501" }
```

### Money in responses
All money in API responses is in **rupees** (float) for backward compatibility.
All money in the database is in **paise** (integer).
When reading API responses, multiply by 100 to get paise for calculations.

---

## AUTH

### `POST /auth/register`
Create a new user account.

**Request:**
```json
{
  "name": "Rajesh Kumar",
  "email": "rajesh@pharmacy.com",
  "password": "SecurePass@123",
  "role": "cashier"
}
```

**Response:**
```json
{
  "user": { "id": "uuid", "name": "Rajesh Kumar", "email": "...", "role": "cashier" },
  "token": "eyJhbGciOiJIUzI1NiJ9..."
}
```

---

### `POST /auth/login`
Login with email and password.

**Request:**
```json
{ "email": "admin@pharmacy.com", "password": "Admin@123" }
```

**Response:** Same as register.

**Errors:**
- `400` — Invalid credentials

---

### `POST /auth/forgot-password`
Self-service password reset, step 1 (added Sep 16, 2026 — docs/15_ROADMAP.md
Auth Overhaul #6). Public, unauthenticated.

**Request:**
```json
{ "email": "admin@pharmacy.com" }
```

**Response:** Always the same generic message, whether or not the email
matches a real, active account (anti-enumeration):
```json
{ "message": "If an account exists for that email, a password reset link has been sent." }
```

If a real, active account matches, the response also includes
`dev_reset_link` — no real SMTP/SendGrid service is wired in yet (a
deliberate, asked-not-assumed decision — needs real credentials only
Abinash can provide), so the reset link is returned directly instead of
emailed, and also logged server-side:
```json
{ "message": "...", "dev_reset_link": "/reset-password?token=<raw-token>" }
```

---

### `POST /auth/reset-password`
Self-service password reset, step 2. Public, unauthenticated — the token
itself (single-use, SHA-256-hashed, expires 1 hour after creation) is the
authorization, not a JWT.

**Request:**
```json
{ "token": "<raw-token-from-the-reset-link>", "new_password": "NewPass123" }
```

**Response:**
```json
{ "message": "Password reset successfully. You can now log in with your new password." }
```

**Errors:**
- `400` — Token is missing, unknown, already used, or expired: `"This reset link is invalid or has expired."`

---

### `POST /auth/session`
> ⚠️ **Tech debt, not a designed feature.** This is leftover scaffolding from
> the app-builder template this project started from. On session creation it
> calls out to a **third-party demo backend**
> (`https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data`) to
> validate an `X-Session-ID` header, auto-provisions a user from whatever
> that external service returns, and sets a `session_token` cookie — a
> completely separate auth path from `POST /auth/login`'s JWT flow. It is
> still live and still called by `frontend/src/App.js` (the `session_id=`
> URL-hash handler). A production auth flow should not depend on an external
> demo service. Flagged in `docs/13_DEPLOYMENT.md` pre-launch blockers —
> decide whether to remove this path entirely or replace it with a real SSO
> integration before launch.

Creates or logs in a user from an external session lookup (see warning
above). Sets an httpOnly `session_token` cookie.

---

### `GET /auth/me`
Get current authenticated user.

**Response:** corrected Sep 19, 2026 — this doc claimed a `pharmacy_id` field
that has never actually been in the response (found while writing a
backend test that tried to read it); `is_super_admin` is a computed flag
(role is `"admin"`, or the user has the `*` wildcard permission), not a
raw column:
```json
{ "id": "uuid", "email": "...", "name": "Rajesh", "role": "doctor", "is_active": true,
  "is_admin": false, "is_super_admin": false, "permissions": ["patient_billing:view", "prescriptions:create"] }
```
`permissions` (Oct 3, 2026) is the role's ticks as a flat `module:action` list — `["*"]` for an admin or wildcard
role. `POST /auth/login`'s `user` object carries the same `is_admin` / `is_super_admin` / `permissions`. The frontend
shows or hides buttons from this list; the backend still enforces on every call.
Need the pharmacy_id for the current user? `GET /users/{id}` (with the
`id` from this response) returns it.

---

### `POST /auth/logout`
Invalidate session (client should also clear localStorage).

---

## BILLING

### `POST /bills`
Create a bill (draft or settled).

**Request:**
```json
{
  "status": "paid",
  "invoice_type": "SALE",
  "customer_name": "Patient Name",
  "customer_mobile": "9876543210",
  "doctor_name": "Dr. Sharma",
  "items": [
    {
      "product_id": "uuid",
      "product_sku": "PARA500",
      "product_name": "Crocin 500mg",
      "batch_id": "uuid",
      "batch_number": "BN240501",
      "quantity": 2,
      "unit_price": 12.50,
      "mrp": 12.50,
      "disc_percent": 0,
      "gst_percent": 5
    }
  ],
  "discount": 0,
  "tax_rate": 5,
  "payment_method": "cash",
  "payments": [{ "amount": 26.25, "payment_method": "cash" }]
}
```

**Key rules:**
- `status: "draft"` → no bill number assigned, stock not deducted
- `status: "paid"` or `"due"` → real bill number assigned, stock deducted
- Schedule H1 items → `doctor_name` required or returns `400`
- `invoice_type: "SALES_RETURN"` → creates return bill with RTN- prefix

**Response:** Full bill object with bill_number, items, totals.

**Errors:**
- `400` — Schedule H1 drug without doctor name
- `400` — Insufficient stock in batch

---

### `GET /bills`
List bills with pagination and filters.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Per page (max 100) |
| `status` | string | — | `paid`, `due`, `draft`, `partial` |
| `invoice_type` | string | `SALE` | `SALE`, `SALES_RETURN` |
| `start_date` | date | — | `YYYY-MM-DD` |
| `end_date` | date | — | `YYYY-MM-DD` |
| `search` | string | — | Bill number or customer name |
| `customer_id` | uuid | — | Filter by customer |

**Response:**
```json
{
  "data": [
    {
      "id": "uuid",
      "bill_number": "INV-000042",
      "bill_date": "2026-04-18",
      "customer_name": "Ramesh",
      "total_amount": 262.50,
      "paid_amount": 262.50,
      "due_amount": 0,
      "status": "paid",
      "payment_method": "cash"
    }
  ],
  "pagination": { "page": 1, "total": 340, ... }
}
```

---

### `GET /bills/{bill_id}`
Get full bill with all line items.

---

### `PUT /bills/{bill_id}`
Update a bill. Works on `draft`, `paid`, or `due` status — corrected
Sep 18, 2026, this doc previously said "draft only" and drifted the same
day the real behavior changed underneath it (`docs/10_API.md`'s own rule
says new/changed endpoint behavior is documented in the same PR — this
one wasn't, until this pass caught it).

**On a `draft` bill:** ordinary edit, same rules as `POST /bills`.

**On an already-finalized (`paid`/`due`) bill:** a same-day correction
window — items/pricing only, payment amount/method preserved, old stock
movements reversed and new ones applied, logged as a `financial_edit`
audit entry. Returns `400` once either holds: a Sales Return already
exists against this bill, or that day's Day-End Closing has already run.
See `docs/07_BUSINESS_LOGIC.md` (search "same-day correction") for the
full rule and `docs/15_ROADMAP.md`'s Billing table for why it was built.

**Errors:**
- `400` — Bill status isn't `draft`/`paid`/`due`
- `400` — "This bill has a return recorded against it and can no longer be edited."
- `400` — "This bill's day has already been closed and can no longer be edited."

---

### `GET /bills/{bill_id}/pdf`
Download bill as PDF.
**Response:** `application/pdf` stream.

---

### `POST /payments`
Record payment against a due bill.

**Request:**
```json
{
  "invoice_id": "bill-uuid",
  "amount": 450.00,
  "payment_method": "upi",
  "reference_number": "UPI-TX-123456"
}
```

---

### `GET /payments`
List payments for a bill. **Query params:** `invoice_id` (required — returns
`[]` without it). Payments aren't a separate ledger table; this derives a
single synthetic entry from `bills.amount_paid_paise` / `payment_method`.

---

### `POST /refunds`
Record refund for a sales return bill.

**Request:**
```json
{
  "return_invoice_id": "return-bill-uuid",
  "original_invoice_id": "original-bill-uuid",
  "amount": 125.00,
  "refund_method": "cash",
  "reason": "Expired product"
}
```

---

### `GET /refunds`
List refunds. **Query params:** `return_invoice_id`, `original_invoice_id`.
Like `GET /payments`, this is derived (from bill status + audit logs), not a
dedicated refunds table.

---

## INVENTORY

### `GET /inventory`
List all products with current stock levels.

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| `page` | int | — |
| `page_size` | int | — |
| `search` | string | Product name, SKU, generic name |
| `category` | string | Filter by category |
| `drug_schedule` | string | `OTC`, `H`, `H1`, `X` |
| `stock_status` | string | `low_stock`, `out_of_stock`, `near_expiry`, `expired`, `healthy` |
| `location` | string | Storage location filter |

---

### `GET /inventory/filters`
Get available filter options (distinct values for dropdowns).

**Response:**
```json
{
  "categories": ["Antibiotics", "Analgesics", ...],
  "dosage_types": ["Tablet", "Syrup", ...],
  "schedule_types": ["OTC", "H", "H1"],
  "gst_rates": [0, 5, 12, 18],
  "locations": ["Rack A", "Rack B", ...]
}
```

---

### `GET /products/meta`
Dropdown source of truth for the Add Medicine form — categories (with fixed
HSN + description), valid GST slabs, dosage forms. Read this instead of
hardcoding the same lists in frontend constants.

**Response:**
```json
{ "categories": [...], "gst_rates": [0, 5, 12, 18, 28], "dosage_forms": [...] }
```

---

### `POST /products/bulk-update`
Bulk-edit one field across many products by SKU. Admin/manager only.

**Request:**
```json
{ "skus": ["PARA500", "AMOX250"], "field": "category", "value": "Analgesics" }
```

**Allowed `field` values:** `storage_location` (`location` accepted as
alias), `gst_rate` (`gst_percent` accepted as alias), `category`,
`drug_schedule` (`schedule` accepted as alias), `brand`. Any other field
name returns `400`.

---

### `POST /products`
Create a new product in the master.

**Request:**
```json
{
  "name": "Crocin 500mg",
  "generic_name": "Paracetamol",
  "sku": "PARA500",
  "category": "Analgesics",
  "drug_schedule": "OTC",
  "dosage_form": "Tablet",
  "units_per_pack": 10,
  "hsn_code": "3004",
  "gst_rate": 5,
  "reorder_level": 20
}
```

---

### `GET /products`
List products (master, without stock levels).

**`pharmacy_id`** (optional query param, added Sep 27, 2026 — HQ-buyer
picker, `docs/26_MULTI_CHAIN_SCOPE.md` Section 3 #3): list a different
store's products than the caller's active session (via
`resolve_store_override` in `routers/auth_helpers.py`). Requires a real
`user_store_roles` grant at that store — 403 otherwise, no specific
permission needed (read-only). Omit for the unchanged, common case.

---

### `GET /products/{product_id}`
Get single product detail.

---

### `PUT /products/{product_id}`
Update product master data.

---

### `DELETE /products/{product_id}`
Soft delete a product (`deleted_at` set, `is_active = false`).

---

### `GET /products/search-with-batches`
Search products and return with available batches. Used by the billing screen.

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Search term (name, generic, barcode) |
| `pharmacy_id` | uuid | — |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Crocin 500mg",
    "generic_name": "Paracetamol",
    "gst_rate": 5,
    "batches": [
      {
        "id": "uuid",
        "batch_number": "BN240501",
        "expiry_date": "2026-06-30",
        "qty_on_hand": 50,
        "mrp_per_unit": 12.50,
        "cost_price_per_unit": 9.80
      }
    ]
  }
]
```

---

### `GET /products/barcode/{barcode}`
Look up product by barcode. Used by barcode scanner.

---

### `GET /products/{sku}/transactions`
Get all purchase and sale transactions for a product.

---

### Bulk upload (Excel) — `frontend/src/components/ExcelBulkUploadWizard`
Defined in `backend/utils/excel.py` (a separate `excel.router`, not
`inventory.router` — same `/api` prefix, so paths still read as
`/inventory/bulk-upload/*`). A 4-step wizard: download template → upload &
auto-detect columns → validate rows → import.

| Endpoint | Notes |
|----------|-------|
| `GET /inventory/bulk-upload/template` | Downloads an `.xlsx` template with the expected columns |
| `POST /inventory/bulk-upload/parse` | Upload a file (`multipart/form-data`); auto-detects column mapping by header keyword matching (see `COLUMN_KEYWORDS` in `excel.py`) |
| `POST /inventory/bulk-upload/validate` | `{ job_id, column_mapping }` — validates every row against required fields (`sku`, `name`, `price`, `quantity`, `expiry_date`, `batch_number`) |
| `POST /inventory/bulk-upload/import` | `{ job_id, import_valid_only }` — runs as a background task |
| `GET /inventory/bulk-upload/progress/{job_id}` | Poll for import progress |
| `GET /inventory/bulk-upload/error-report/{job_id}` | Rows that failed validation/import |

**Note:** job state is an in-memory dict (`bulk_upload_jobs` in `excel.py`) —
lost on backend restart, and won't work correctly behind more than one
backend worker/replica.

---

## STOCK BATCHES

### `POST /stock/batches`
Create a new batch (manual stock entry, not through purchase).

**Request:**
```json
{
  "product_id": "uuid",
  "batch_number": "BN240501",
  "expiry_date": "2026-06-30",
  "quantity": 100,
  "mrp_per_unit": 12.50,
  "cost_price_per_unit": 9.80
}
```

---

### `GET /stock/batches`
List batches, optionally filtered by product.

**Query params:** `product_id`, `include_zero_qty` (boolean)

---

### `GET /stock/batches/{batch_id}`
Get single batch.

---

### `GET /stock/batches/{batch_id}/origin-purchase`
Added Sep 25, 2026 — resolves the confirmed purchase a batch came from
(via `PurchaseItem.batch_id`), so a near-expiry/expired batch can be
returned to its supplier without already knowing which purchase it was.
Advisory only.

**Response:**
```json
{ "found": true, "purchase_id": "uuid", "purchase_number": "PUR-2026-0001" }
```
Or `{"found": false}` if this batch wasn't created via a confirmed
purchase (e.g. added directly via `POST /stock/batches`).

---

### `PUT /stock/batches/{batch_id}`
Update batch (MRP, cost price, expiry).

---

### `DELETE /stock/batches/{batch_id}`
Soft delete a batch. Only allowed if `qty_on_hand = 0`.

---

### `POST /batches/{batch_id}/adjust`
Manual stock adjustment.

**Request:**
```json
{
  "adjustment_quantity": -5,
  "reason": "Damaged stock",
  "notes": "Found 5 strips damaged during audit"
}
```

---

### `POST /batches/{batch_id}/writeoff-expiry`
Write off an expired batch.

**Request:**
```json
{ "quantity": 20, "reason": "Expired" }
```

---

### `POST /stock-movements`
Record a manual movement directly against a batch (used by adjust/writeoff
flows internally, and available standalone).

**Request:**
```json
{ "batch_id": "uuid", "movement_type": "adjustment", "qty_delta_units": -5, "ref_type": "manual", "reason": "Damaged stock" }
```

---

### `GET /stock-movements`
List stock movements (the ledger).

**Query params:** `product_id`, `batch_id`, `movement_type`, `start_date`, `end_date`, `page`, `page_size`

---

## STOCK TRANSFERS

Added Sep 26, 2026 — multi-chain Phase 2 Step 5, `docs/26_MULTI_CHAIN_SCOPE.md`.
Cross-store stock transfer, instant (v1, no in-transit state), admin-only.

### `POST /stock-transfers`
Moves stock from the caller's own pharmacy to another store in the same
chain. Auto-creates the destination product if that SKU doesn't exist
there yet (products are stored separately per store); matches the
destination batch by batch number, or creates one preserving the exact
expiry/cost/MRP. Writes an audit-log entry on both the source
(`stock_transfer_out`) and destination (`stock_transfer_in`) pharmacy.
400 if not enough stock or destination == source; 403 if the destination
isn't in the caller's chain or the caller isn't an admin.

**Only allowed between two stores with a confirmed, matching GSTIN**
(added Sep 27, 2026 — `docs/26_MULTI_CHAIN_SCOPE.md` Step 5b, after
confirming moving stock between different-GSTIN stores is a taxable
"supply" needing a tax invoice and typically a Wholesale Drug License,
neither of which this app generates or verifies). 400 if either store's
GSTIN is unset; 403 if the two GSTINs differ. `is_cross_gstin` in the
response is now always `false` for a new transfer — the field stays on
the model only for transfers made before this change.

**Request:**
```json
{
  "destination_pharmacy_id": "uuid", "notes": "optional",
  "items": [{"product_sku": "SKU-1", "batch_number": "B-1", "quantity": 10}]
}
```

**Response:**
```json
{
  "id": "uuid", "transfer_number": "TRF-2026-ABC123",
  "source_pharmacy": "Store A", "destination_pharmacy": "Store B",
  "is_cross_gstin": false,
  "items": [{"product_sku": "SKU-1", "product_name": "...", "batch_number": "B-1", "quantity": 10}]
}
```

### `GET /stock-transfers`
Lists every transfer where the caller's own pharmacy is either the
source or the destination, each tagged `direction: "out" | "in"`.

### `POST /stock-transfers/{transfer_id}/reverse`
Reverses a transfer: restores the source batch, reduces the destination
batch. Admin-only. 400 if already reversed, or if the destination
batch's on-hand quantity is less than what this transfer added (some of
it has already been sold/used elsewhere) — checked against real stock,
not a time limit.

---

## SALES RETURNS

### `POST /sales-returns`
Create a sales return. `original_bill_id` is **required** (Sep 23, 2026) —
a request with it missing/null always 400s ("A return must be created from
an existing bill…"), for every role. No manual/no-bill return path exists
anymore. Each item's `qty` is capped at what's *still* returnable on that
batch — the original billed quantity minus whatever earlier, separate
returns on this same bill already took (`PUT /sales-returns/{id}` with
`financial_edit=true` enforces the identical cap). Exceeding it 400s with
the remaining quantity in the message.

**Request:**
```json
{
  "original_bill_id": "bill-uuid",
  "return_reason": "Wrong medicine dispensed",
  "items": [
    {
      "bill_item_id": "item-uuid",
      "product_id": "product-uuid",
      "batch_id": "batch-uuid",
      "quantity": 2,
      "return_to_stock": true
    }
  ],
  "refund_method": "cash"
}
```

---

### `GET /sales-returns`
List sales returns with pagination.

**Query params:** `page`, `page_size`, `start_date`, `end_date`, `search`

---

### `GET /sales-returns/{return_id}`
Get single sales return with items.

---

### `PUT /sales-returns/{return_id}`
Edit a sales return. Two edit modes:
- **Non-financial** (note, billed-by) — any user.
- **Financial** (items, amounts) — reverses the old stock movements, deletes
  the old return items, and rebuilds them from the request. Requires the
  `allow_financial_edit_return` permission (admins always have it — see
  `PUT /roles/{role_id}/permissions/returns` under USERS & ROLES).

---

## PURCHASES

### `POST /purchases`
Create a purchase (draft or confirmed).

**Request:**
```json
{
  "supplier_id": "uuid",
  "supplier_invoice_number": "INV-2026-1234",
  "supplier_invoice_date": "2026-04-15",
  "status": "confirmed",
  "items": [
    {
      "product_sku": "PARA500",
      "batch_no": "BN240501",
      "expiry_date": "2026-06-30",
      "qty_units": 100,
      "mrp_per_unit": 12.50,
      "cost_price_per_unit": 10.00,
      "gst_percent": 5
    }
  ]
}
```
`cost_price_per_unit` is the PTR the pharmacist types off the supplier's
invoice — see `docs/02_GLOSSARY.md`'s PTR entry. There is no separate
`ptr_per_unit` field; one was removed from this endpoint Sep 28, 2026 (it
duplicated `cost_price_per_unit` with no real second value behind it).

**Key rule:** `status: "confirmed"` creates stock batches immediately.

**`pharmacy_id`** (optional, added Sep 27, 2026 — HQ-buyer picker,
`docs/26_MULTI_CHAIN_SCOPE.md` Section 3 #3): places the purchase at a
different store than the caller's active session. Omit for the
unchanged, common case (creates at the caller's own active store).
When set, requires a real `user_store_roles` grant at that store AND
`purchases:create` there (via `resolve_store_override_for_write` in
`routers/auth_helpers.py`) — 403 otherwise. `supplier_id`/`product_sku`
in `items` must already exist AT the target store, same as always.

---

### `GET /purchases`
List purchases.

**Query params:** `page`, `page_size`, `status`, `payment_status`, `supplier_id`, `start_date`, `end_date`

---

### `GET /purchases/{purchase_id}`
Get single purchase with items. Each item now also returns
`units_per_pack` (added Sep 24, 2026 — stored at confirm time, was never
returned before; the Purchase entry screen's Pack/Unit toggle needs it
when a draft is reloaded for editing, see `docs/07_BUSINESS_LOGIC.md`).

`POST/PUT /purchases`'s per-item request also accepts an optional
`received_qty_units` (added Sep 25, 2026 — short/excess supply; `null`/
omitted = no discrepancy, the default). `received_qty_units` now also
appears on each item in the response, reflecting what was actually
confirmed (previously always 0, a dead field — see `docs/07_BUSINESS_LOGIC.md`).

### `GET /purchases/last-purchase-price`
Added Sep 25, 2026 — price-change warning. Advisory only, same shape as
`GET /purchases/check-duplicate-invoice` (undocumented before this, also
static-registered ahead of `/purchases/{purchase_id}`).

**Query params:** `product_sku` (required)

**Response** (most recent CONFIRMED purchase of this product, any supplier):
```json
{ "found": true, "cost_price_per_unit": 8.00, "mrp_per_unit": 18.00, "purchase_date": "2026-09-01" }
```
Or `{"found": false}` if this product has never been purchased before
(or only ever as a draft — drafts never count).

---

### `PUT /purchases/{purchase_id}`
Update purchase (only `draft` status).

---

### `POST /purchases/{purchase_id}/pay`
Record payment to supplier.

**Request:**
```json
{
  "amount": 5000.00,
  "payment_method": "bank_transfer",
  "reference_number": "NEFT-123456",
  "payment_date": "2026-04-18"
}
```

---

## PURCHASE RETURNS

### `GET /purchases/{purchase_id}/items-for-return`
Get purchase items eligible for return.

---

### `POST /purchase-returns`
Create a purchase return (debit note).

---

### `GET /purchase-returns`
List purchase returns.

---

### `GET /purchase-returns/{return_id}`
Get single purchase return with items.

---

### `PUT /purchase-returns/{return_id}`
Edit a purchase return — `{ edit_type: "financial" | "non_financial", note, billed_by }`.

---

### `POST /purchase-returns/{return_id}/confirm`
Confirm a purchase return (deducts stock).

---

## CUSTOMERS

### `POST /customers`
Create a customer.

**Request:**
```json
{
  "name": "Ramesh Kumar",
  "phone": "9876543210",
  "customer_type": "retail"
}
```

---

### `GET /customers`
List customers with search and pagination.

**Query params:** `search`, `customer_type`, `page`, `page_size`

---

### `GET /customers/search`
Lightweight typeahead — `?q=` matches name or phone, returns up to 100,
no pagination. Used by `PatientCombobox` on the billing screen. Different
from `GET /customers?search=`, which is the paginated list-page search.

---

### `GET /customers/{customer_id}`
Get customer detail.

---

### `GET /customers/{customer_id}/stats`
Get customer purchase history stats.

**Response:** (corrected Sep 26, 2026 — this doc previously listed field
names `total_bills`/`total_spent`/`outstanding`/`last_purchase_date`,
none of which the real endpoint returns or ever returned)
```json
{
  "total_purchases": 42,
  "total_value": 18500.00,
  "last_purchase": "10/04/2026"
}
```

---

### `PUT /customers/{customer_id}`
Update customer.

---

### `DELETE /customers/{customer_id}`
Soft delete customer.

---

## DOCTORS

### `POST /doctors`
Create a doctor record.

### `GET /doctors`
List doctors (search by name).

### `PUT /doctors/{doctor_id}`
Update doctor.

### `DELETE /doctors/{doctor_id}`
Soft delete.

---

## SUPPLIERS

### `GET /suppliers`
List all suppliers.

**`pharmacy_id`** (optional query param, added Sep 27, 2026 — HQ-buyer
picker, `docs/26_MULTI_CHAIN_SCOPE.md` Section 3 #3): list a different
store's suppliers than the caller's active session (via
`resolve_store_override`). Requires a real `user_store_roles` grant at
that store — 403 otherwise. Omit for the unchanged, common case.

### `POST /suppliers`
Create supplier.

**`pharmacy_id`** (optional body field, added Sep 27, 2026 — same HQ-buyer
picker): create the supplier at a different store than the caller's
active session (via `resolve_store_override_for_write`). Requires a real
grant AND `suppliers:create` at that store — 403 otherwise. Omit for the
unchanged, common case.

### `GET /suppliers/{supplier_id}`
Get supplier detail.

### `GET /suppliers/{supplier_id}/summary`
Get supplier purchase history and outstanding.

### `PUT /suppliers/{supplier_id}`
Update supplier.

### `DELETE /suppliers/{supplier_id}`
Soft delete.

### `PATCH /suppliers/{supplier_id}/toggle-status`
Activate or deactivate supplier.

---

## REPORTS

### `GET /reports/dashboard`
KPIs for the dashboard.

**Response:**
```json
{
  "today_sales": 24500.00,
  "today_bills": 42,
  "low_stock_count": 8,
  "near_expiry_count": 15,
  "outstanding_receivable": 12000.00,
  "monthly_sales": 485000.00
}
```

---

### `GET /reports/sales-summary`
Sales summary by date range.

**Query params:** `start_date`, `end_date`

---

### `GET /reports/sales`
Detailed sales report.

**Query params:** `start_date`, `end_date`, `page`, `page_size`

---

### `GET /reports/gst`
GST report for GSTR-1 filing.

**Query params:** `start_date`, `end_date`, `scope` (optional, `store`|`chain`,
default `store` — added Sep 27, 2026, `docs/26_MULTI_CHAIN_SCOPE.md`
Section 6 #6b). `chain` sums every store in the caller's chain's own
already-independently-filed GST numbers into one display-only view —
each store still generates and files its own separate return, unaffected.
Response gains `scope` and `store_count`, same convention as
`GET /analytics/dashboard`.

---

### `GET /reports/supplier-analytics`
Added Sep 25, 2026 — UC-P41. Cross-supplier ranking, payment performance,
return rate, and price comparison. Previously the only per-supplier view
was `GET /suppliers/{id}/summary` — one supplier at a time.

**Query params:** `from_date`, `to_date` (both optional — omitted = all time)

**Response:**
```json
{
  "summary": { "total_suppliers": 2, "total_purchase_value": 945.00 },
  "data": [
    {
      "supplier_name": "Reliable Distributors", "total_purchases": 1,
      "total_purchase_value": 525.00, "total_returns": 0,
      "total_return_value": 0.0, "return_rate_percent": 0.0,
      "avg_days_to_pay": 0.0, "overdue_amount": 0.0,
      "products_supplied": 1, "higher_priced_products_count": 0
    }
  ]
}
```
`data` is sorted by `total_purchase_value` descending — row position is
the rank. `avg_days_to_pay` is `null` when the supplier has no fully paid
purchase in range yet.

---

### `GET /reports/purchase-variance`
Added Sep 25, 2026 — UC-P38. Two independent datasets: quantity variance
(short/excess delivery) and adjustment variance (manual invoice
corrections).

**Query params:** `from_date`, `to_date` (both optional — omitted = all time)

**Response:**
```json
{
  "summary": {
    "total_quantity_variances": 1, "total_short_qty": 5, "total_excess_qty": 0,
    "total_adjustment_variances": 1, "total_adjustment_amount": 12.75
  },
  "data": [
    {
      "purchase_number": "PUR-2026-0003", "purchase_date": "25/09/2026",
      "supplier_name": "Reliable Distributors", "product_name": "Paracetamol 650",
      "batch_number": "B-001", "qty_ordered": 20, "qty_received": 15,
      "variance_qty": -5, "variance_type": "short"
    }
  ],
  "adjustment_variance": [
    { "purchase_number": "PUR-2026-0003", "purchase_date": "25/09/2026",
      "supplier_name": "Reliable Distributors", "adjustment_amount": 12.75 }
  ]
}
```
`data` holds quantity variance (exportable via the Reports page's generic
CSV/Excel export); `adjustment_variance` is a secondary, view-only table
— same split as the margin report's `data`/`by_category`.

---

### `GET /reports/batch-purchases`
Added Sep 25, 2026 — UC-P34. Traces every purchased batch back to its
purchase and supplier, via the real `PurchaseItem.batch_id` FK.

**Query params:** `from_date`, `to_date` (both optional, filter on
`purchase_date` — omitted = all time)

**Response:**
```json
{
  "summary": { "total_batches": 3, "total_units": 85, "active_batches": 3 },
  "data": [
    {
      "batch_number": "B-001", "product_name": "Paracetamol 650", "sku": "SKU-1",
      "purchase_number": "PUR-2026-0001", "purchase_date": "25/09/2026",
      "supplier_name": "Reliable Distributors", "qty_received": 50,
      "cost_price_per_unit": 10.00, "mrp_per_unit": 20.00,
      "current_stock": 50, "expiry_date": "01/01/2030", "is_active": true
    }
  ]
}
```
`current_stock` is live (`StockBatch.quantity_on_hand`) — reflects any
sales/adjustments since purchase, not frozen at purchase time.

---

### `GET /reports/purchase-payments`
Added Sep 25, 2026 — UC-P37. Lists every real (non-reversed) supplier
payment across all purchases, date-filtered, with a by-payment-method
breakdown. Previously payments were only queryable one purchase at a time
(`GET /purchases/{id}/payments`).

**Query params:** `from_date`, `to_date` (both optional — omitted = all time)

**Response:**
```json
{
  "summary": { "total_payments": 12, "total_amount": 45000.00 },
  "by_method": [
    { "payment_method": "cash", "count": 8, "amount": 30000.00 },
    { "payment_method": "upi", "count": 4, "amount": 15000.00 }
  ],
  "data": [
    {
      "payment_date": "20/09/2026", "purchase_number": "PUR-2026-0042",
      "supplier_name": "Acme Pharma", "payment_method": "cash",
      "reference_number": "", "notes": "", "amount": 5000.00
    }
  ]
}
```

**Response:**
```json
{
  "summary": {
    "total_taxable": 450000.00,
    "total_cgst": 11250.00,
    "total_sgst": 11250.00,
    "total_gst": 22500.00,
    "grand_total": 472500.00
  },
  "hsn_wise": [
    {
      "hsn_code": "3004",
      "description": "Medicaments",
      "taxable_amount": 380000.00,
      "gst_rate": 5,
      "cgst": 9500.00,
      "sgst": 9500.00
    }
  ]
}
```

---

### `GET /reports/low-stock`
Products below reorder level.

### `GET /reports/expiry`
Batches expiring within threshold days.

---

## ANALYTICS
Dashboard-facing aggregates — distinct from `/reports/*` above (which are
export/compliance-oriented). All money fields are rupees (float), computed
from `_paise` columns server-side.

### `GET /analytics/summary`
Gross sales, returns, net sales, pending (due) amount, today's sales, draft
count — the tiles at the top of the Dashboard.

### `GET /analytics/daily`
Per-day sales/returns/net for the last N days. **Query params:** `days` (default `7`).

### `GET /analytics/dashboard`
Wider dashboard payload — week/month/yesterday/last-week/last-month/30-day
comparisons. **Query params:** `from_date`, `to_date` (optional custom
trend range); `scope` (`store` default, or `chain` — added Sep 26, 2026,
`docs/26_MULTI_CHAIN_SCOPE.md` Step 4). `scope=chain` sums every summable
number across every store in the caller's chain (or just their own store,
unchanged, if they aren't in one). Single-pharmacy config (settings,
drug license alert) always stays on the caller's own home store
regardless of `scope`. Response includes `scope` and `store_count`.

### `GET /analytics/purchases`
Purchase totals + purchase-return totals for a date range. **Query params:**
`from_date`, `to_date`, `scope` (`store` default, or `chain` — same Step 4
rollup as `/analytics/dashboard` above, since this feeds the Dashboard's
Purchases summary card).

> ⚠️ **This route is defined twice** — in `backend/routers/reports.py:1274`
> and again in `backend/routers/sales_returns.py:938`. FastAPI matches the
> first registration, and `main.py` includes `reports.router` (line 63)
> before `sales_returns.router` (line 67), so the `reports.py` version
> always wins — the copy in `sales_returns.py` is dead code, unreachable.
> Not fixed as part of this doc pass (code change, not a doc one); worth a
> follow-up to delete the dead copy from `sales_returns.py` so a future
> edit to "the" `/analytics/purchases` doesn't silently target the wrong
> file.

---

### `GET /backup/export`
Admin-only. Dumps every row (this pharmacy only) from `products`, `bills`,
`purchases`, `customers`, `doctors`, `suppliers` as JSON. Manual substitute
for the "No automated backups" gap tracked in `docs/13_DEPLOYMENT.md`
pre-launch blockers — not a scheduled/automated backup itself.

---

## COMPLIANCE

### `GET /compliance/schedule-h1-register`
Schedule H1 register for drug inspector compliance.

**Query params:** `start_date`, `end_date`, `page`, `page_size`

**Response:**
```json
{
  "data": [
    {
      "supply_date": "2026-04-18",
      "patient_name": "Mohan Lal",
      "prescriber_name": "Dr. Sharma",
      "product_name": "Augmentin 625mg",
      "batch_number": "BN240601",
      "quantity": 6,
      "bill_number": "INV-000042"
    }
  ]
}
```

---

## SETTINGS

### `GET /settings`
Get pharmacy settings.

### `PUT /settings`
Update pharmacy settings.

### `GET /settings/bill-sequence`
Get current bill sequence configuration.

**Response:**
```json
{
  "prefix": "INV",
  "current_sequence": 42,
  "next_number": 43,
  "sequence_length": 6,
  "preview": "INV-000043"
}
```

### `PUT /settings/bill-sequence`
Update bill sequence settings.

**Request:**
```json
{
  "prefix": "INV",
  "starting_number": 100,
  "sequence_length": 6
}
```

### `GET /settings/bill-sequence/all`
List all sequence types (INV, RTN, etc.)

---

## USERS & ROLES

### `GET /users`
List all users in the pharmacy.

### `POST /users`
Create a new user. Body: `email`, `name`, `password`, `role`, optional `is_admin` (default `false`).

### `GET /users/{user_id}`
Get single user detail. Admin only.

### `PUT /users/{user_id}`
Update user (name, email, role, active status, `is_admin`). A user cannot remove their own admin access (400). `is_admin` users keep their role and get every permission; `/auth/me` and login return `is_admin` and `is_super_admin: true` for them.

### `DELETE /users/{user_id}`
Deactivate user (soft delete).

### `PUT /users/me/change-password`
Change own password.

**Request:**
```json
{ "current_password": "old", "new_password": "new" }
```

### `GET /users/me/stores`
Added Sep 26, 2026 — multi-chain Phase 2 groundwork (`docs/26_MULTI_CHAIN_SCOPE.md`).
Every store the caller has access to, for the sidebar switcher. Always
returns at least one row. `gstin` (added Sep 27, 2026, Step 5b) lets the
frontend pre-filter valid stock-transfer destinations before the caller
fills in a whole transfer, since `POST /stock-transfers` only allows
matching-GSTIN stores.

**Response:**
```json
[
  {"pharmacy_id": "uuid", "pharmacy_name": "Store A", "role_name": "admin", "is_active": true, "gstin": "29AAAAA0000A1Z5"},
  {"pharmacy_id": "uuid", "pharmacy_name": "Store B", "role_name": "manager", "is_active": false, "gstin": null}
]
```

### `POST /users/me/switch-store`
Added Sep 26, 2026, same groundwork. Makes another store the caller
already has a `user_store_roles` grant for their active one — updates
`users.pharmacy_id`/`role_id` directly (not a new session/token; those two
columns are read fresh on every request). 403 if no grant exists for the
target store.

**Request:** `{ "pharmacy_id": "uuid" }`

### `GET /users/{user_id}/store-access`
Added Sep 26, 2026 — Step 3, `docs/26_MULTI_CHAIN_SCOPE.md`. Lists every
`user_store_roles` grant for that user (scoped via `get_owned_or_404` to
the caller's own pharmacy — the target user must already be one of the
caller's own team members). Admin only.

**Response:**
```json
[
  {"pharmacy_id": "uuid", "pharmacy_name": "Store A", "role_name": "admin"},
  {"pharmacy_id": "uuid", "pharmacy_name": "Store B", "role_name": "manager"}
]
```

### `POST /users/{user_id}/store-access`
Grants (or updates the role for) the target user's access to a store.
Admin only. Rejects (400/403) if `pharmacy_id` isn't the admin's own
pharmacy or another store in the admin's own chain (`_same_chain_or_self`)
— never an arbitrary pharmacy elsewhere in the system. Audit-logged
(`grant_store_access`).

**Request:** `{ "pharmacy_id": "uuid", "role": "manager" }`

### `DELETE /users/{user_id}/store-access/{pharmacy_id}`
Revokes the target user's access to that store. Admin only. Rejects with
`400` if `pharmacy_id` is the target's current active store
(`users.pharmacy_id`), or if it's their only remaining grant — a user can
never be left with zero store access. Audit-logged
(`revoke_store_access`).

### `GET /pharmacies/stores`
Added Sep 26, 2026, same Step 3. Lists every pharmacy in the caller's
chain — just the caller's own pharmacy if `chain_id` is still `NULL`
(the common case; nothing forces a chain to exist). Permission-exempt
(any authenticated user can see their own chain's store list, same as
the switcher).

**Response:**
```json
[{"pharmacy_id": "uuid", "name": "Store A", "city": "Bengaluru", "state": "Karnataka"}]
```

### `POST /pharmacies/stores`
Creates a new store under the caller's pharmacy. Admin (or super admin)
only. If the caller's pharmacy has no `chain_id` yet, creates a new
`Chain` (named `"{pharmacy.name} Group"`) and links both pharmacies to
it first — a chain is never created upfront, only lazily on first use.
Auto-grants the creator admin access to the new store. Audit-logged
against the admin's own pharmacy (not the chain).

**Request:**
```json
{
  "name": "Second Store", "address": "2 St", "city": "Testville",
  "state": "Karnataka", "pincode": "560002", "phone": "9877700001",
  "email": null, "gstin": null, "drug_license_number": "DL-2"
}
```

**Response:** `{ "pharmacy_id": "uuid", "name": "Second Store", "chain_id": "uuid" }`

### `GET /permissions`
List every permission flag the system knows about (`ALL_PERMISSIONS`).
Admin only — feeds the role-editor's permission checkboxes.

### `GET /roles`
List all roles with permissions.

### `POST /roles`
Create custom role.

### `GET /roles/{role_id}`
Get single role.

### `PUT /roles/{role_id}`
Update role permissions. System roles (`is_system_role=true`) reject edits with `400`.

### `DELETE /roles/{role_id}`
Delete a custom role. Admin only.

### `GET /roles/{role_name}/permissions/returns`
### `PUT /roles/{role_id}/permissions/returns`
Get/set the one remaining Sales-Return-specific permission flag
(`allow_financial_edit_return`) for a role — admin only for the write.
`allow_manual_returns` removed Sep 23, 2026 along with the manual-return
feature it gated. **Note:** defined in `backend/routers/sales_returns.py`,
not `settings.py`, alongside the rest of the role endpoints above — look
there first if these seem to be missing.

---

## EMR (module #2 — added Oct 2, 2026)

> Routers: `backend/modules/emr/routers/`. Scope: `docs/28_EMR_SCOPE.md`. All endpoints are
> pharmacy-scoped (the caller's own `pharmacy_id`), permission-checked, and audit-logged
> (`entity_type` = `emr_patient` / `emr_schedule` / `emr_appointment`). Deletes are soft.
> Status/type values live in `backend/modules/emr/constants.py`.

### Patients — `patients:view|create|edit|delete`
| Method | Path | Notes |
|--------|------|-------|
| POST | `/emr/patients` | Body: `name` (required), `phone`, `alternate_phone` (≤10 chars), `email`, `date_of_birth`, `age`, `gender`, `blood_group`, `address`, `city`, `allergies`, `notes` |
| GET | `/emr/patients?search=&page=&page_size=` | Search by name/phone. Always paginated: `{data, pagination}` |
| GET | `/emr/patients/{id}` | 404 if deleted or another pharmacy's |
| PUT | `/emr/patients/{id}` | Partial update of the fields above; returns the patient |
| DELETE | `/emr/patients/{id}` | Soft delete |

### Doctors & schedules — `schedules:view|edit`
| Method | Path | Notes |
|--------|------|-------|
| GET | `/emr/doctors` | Active users with role `doctor`, or who have a schedule block. Needs `appointments:view` |
| GET | `/emr/schedules?doctor_user_id=` | Working-hours blocks, ordered weekday/start |
| POST | `/emr/schedules` | `doctor_user_id`, `weekday` (Mon=0..Sun=6), `start_time`/`end_time` (`HH:MM`), `slot_minutes` (5–120, default 15). 409 on overlap with an existing block |
| PUT | `/emr/schedules/{id}` | Partial update; same validation |
| DELETE | `/emr/schedules/{id}` | Soft delete |

### Appointments — `appointments:view|create|edit|cancel`
| Method | Path | Notes |
|--------|------|-------|
| GET | `/emr/slots?doctor_user_id=&date=` | Slot grid from the doctor's schedule: `[{start_time, end_time, available}]` |
| POST | `/emr/appointments` | `patient_id`, `doctor_user_id`, `appointment_date`, optional `start_time`, `reason`. With `start_time` = scheduled (must be an open slot, 422 if off-grid/outside hours, 409 if taken). Without = walk-in (today only). Past dates 422. Token number is per doctor per day |
| GET | `/emr/appointments?date=&date_from=&date_to=&doctor_user_id=&patient_id=&status=` | Day view / live queue. Defaults to today (all dates when `patient_id` is given). Ordered by token. Includes `patient_name`, `doctor_name`. `date_from`+`date_to` (both required together, inclusive, max 31 days, else 422) return a whole range — the calendar's week view |
| GET | `/emr/appointments/{id}` | |
| PUT | `/emr/appointments/{id}` | Reschedule (`appointment_date`, `start_time`, `doctor_user_id`) or edit `reason`. Only while `booked` (else 409) |
| POST | `/emr/appointments/{id}/status` | Body `{status, cancel_reason?}`. Moves: `booked→checked_in→in_consult→completed`; `booked/checked_in→cancelled` (reason required, needs `appointments:cancel`); `booked→no_show`. Invalid move = 409 |

## AUDIT LOGS

### `GET /audit-logs`
List audit log entries.

**Query params:** `entity_type`, `entity_id`, `action`, `page`, `page_size`

### `GET /audit-logs/entity/{entity_type}/{entity_id}`
Get full audit trail for a specific entity.

---

## ERROR CODES

| HTTP Status | Meaning | Common causes |
|-------------|---------|---------------|
| `400` | Bad Request | Validation failure, insufficient stock, H1 without doctor |
| `401` | Unauthorized | Missing or expired JWT token |
| `403` | Forbidden | User role doesn't have permission |
| `404` | Not Found | Resource doesn't exist or was soft-deleted |
| `409` | Conflict | Duplicate bill number, duplicate SKU |
| `422` | Unprocessable Entity | Pydantic validation error (wrong field types) |
| `500` | Server Error | Unexpected backend error — check logs |

---

## HEALTH CHECK

```bash
# Verify backend is running
curl http://localhost:8000/docs       # FastAPI auto-docs
curl http://localhost:8000/openapi.json  # OpenAPI spec
```

### Patient Billing — `/api/patient-billing` (B1 · permissions `patient_billing:view|charge|invoice|collect|void`)
> Plan: `docs/29_BILLING_SCOPE.md`. Separate module; other modules call `modules/patient_billing/service.py` (same rules as these endpoints).
> Audit `entity_type` = `pb_charge_item` / `pb_invoice` / `pb_payment`. Defaults: receptionist = view+charge+invoice+collect, doctor = view, admin = all; pharmacy roles get none.
| Method | Path | Notes |
|--------|------|-------|
| POST | `/charges` | `charge`. Body: `patient_id`, `patient_name`, `patient_uhid`, `source_module`, `description`, `quantity`, `unit_price_paise`, optional `source_ref`/`encounter_ref`/`idempotency_key`. Same key twice → returns the original, no second charge. `pharmacy` source → 422 (not open yet) |
| POST | `/charges/{id}/void` | `void`. Reason required; only `unbilled` (409 if invoiced — cancel the invoice first) |
| GET | `/accounts?status=&source=&search=&page=` | `view`. Billing desk list. `status`: `pending` (default) · `not_invoiced` · `invoiced_unpaid` · `part_paid` · `all`. Each row: `not_invoiced_paise`, `invoiced_unpaid_paise`, `balance_paise`, `sources[]`, `has_part_paid`, `last_activity`. Response adds `totals` |
| GET | `/accounts/{patient_id}` | `view`. One patient's complete bill: `totals`, `charges`, `invoices` (non-cancelled), `payments`. 404 if no account |
| POST | `/invoices` | `invoice`. `{patient_id, charge_item_ids[], discount_paise, counter}` — unbilled charges only, one patient; freezes `lines`. 100% discount → paid immediately |
| GET | `/invoices?status=&patient_id=` · `/invoices/{id}` | `view`. Detail includes `payments` |
| POST | `/invoices/{id}/payments` | `collect`. `{amount_paise, mode, reference}`. Part-payment OK; more than the balance → 422; row-locked so simultaneous payments can never overpay. Returns `{payment, invoice}` with `receipt_number` |
| POST | `/invoices/{id}/cancel` | `void`. Reason required. Unpaid only — an invoice with payments returns 409 (refunds not supported yet). Charges return to `unbilled` |
| POST | `/accounts/{patient_id}/collect` | `invoice` + `collect`. The "Collect" button: invoice chosen charges and pay (full unless `amount_paise`) atomically |
| GET | `/payments?date=&patient_id=` | `view`. Receipts, newest first, paginated |
| GET | `/summary/today?date=` | `view`. `collected_paise`, `receipts`, `by_mode`, `by_counter` |

**Billing desk (B4):** `GET /patient-billing/invoices` also takes `search` (patient name, UHID or invoice number); `GET /patient-billing/payments` rows now carry `patient_name` / `patient_uhid` so receipts read without a second lookup. The desk's Pending tab = `GET /accounts?status=…&source=…&search=` (+ a `status=pending&page_size=1` call for the headline totals); All bills = `/invoices`; Receipts = `/payments?date=`; Day closing = `/summary/today?date=` + `/payments?date=`. Excel exports are built in the browser from the loaded rows.

**Fee on the queue (B3):** every row of `GET /emr/appointments` carries `fee` — `null` (no fee / withdrawn) or `{charge_id, amount_paise, status: unpaid|part_paid|paid, paid_paise, balance_paise, mode, invoice_id, invoice_number}`. EMR gets this from billing's service (`snapshots_by_key`), never from billing tables. The queue's Collect button calls `POST /patient-billing/accounts/{patient_id}/collect` (no invoice yet) or `POST /patient-billing/invoices/{id}/payments` (part-paid invoice); the printable page reads `GET /patient-billing/invoices/{id}`; the "Collected today" card reads `GET /patient-billing/summary/today`.

**EMR consultation fee (B2):** `PUT /emr/doctor-profiles/{id}` accepts `consultation_fee_paise` (0–₹10 lakh, blank clears). When an appointment moves to `checked_in`, that fee is posted as a charge on the patient's account (`idempotency_key = emr:appointment:<id>:consultation`, so one visit is charged once; no fee set = no charge). Moving the visit to `cancelled`/`no_show` voids the charge **only if still unbilled**; once invoiced, the billing desk decides.

### Clinic settings — read: `patients:view` (any clinic user) · write: `emr_settings:edit` (admin)
Audit `entity_type` = `emr_settings` / `emr_doctor_profile`.
| Method | Path | Notes |
|--------|------|-------|
| GET | `/emr/settings` | Created with defaults on first read. Returns clinic profile, `rx_prefix`, `uhid_prefix/digits/next`, `default_slot_minutes`, `patient_form` (field → hidden/optional/required) and `fallback` (pharmacy name/address/phone used while clinic fields are blank) |
| PUT | `/emr/settings` | Partial update. 422 on bad prefix (1-10 letters/numbers/dashes), `uhid_digits` outside 3-10, slot length outside 5-120, unknown form field or state. `patient_form` merges into the existing layout |
| GET | `/emr/doctor-profiles` | Active doctors with `specialty`, `qualification`, `registration_no` |
| PUT | `/emr/doctor-profiles/{user_id}` | Upsert; blank text stored as null. 404 for a user in another clinic |

Patients: every patient gets a `uhid` (clinic prefix + zero-padded counter) at registration; `GET /emr/patients?search=` also matches UHID. Fields set to `required` in the patient-form settings are enforced here (422 "Allergies is required") on create, and on edit for any field being sent.
Prescriptions: the `clinic` block now uses EMR settings (+ `registration_no`, `email`, `footer`), and the response adds `doctor` (specialty/qualification/registration) and `patient_uhid`. `rx_number` uses the clinic's `rx_prefix`; numbering continues across prefix changes.

> `DELETE /emr/patients/{id}` now returns 409 while the patient has an open balance on their bill ("Asha Menon still owes ₹500.00…"); settle or cancel the bills first.

### Prescriptions — `prescriptions:view|create|edit|issue|cancel` (doctor role; receptionist can only view)
One prescription per visit = consultation record + medicine lines. Audit `entity_type` = `emr_prescription`.
| Method | Path | Notes |
|--------|------|-------|
| POST | `/emr/prescriptions` | Body: `appointment_id`. Starts the visit's draft Rx; idempotent — returns the live one if it exists. 409 on a cancelled appointment |
| GET | `/emr/appointments/{id}/prescription` | Read-only: the visit's live (non-cancelled) Rx, 404 if none yet. Needs only `prescriptions:view` — the Rx screen calls this first and `POST /emr/prescriptions` only when it 404s |
| GET | `/emr/prescriptions/{id}` | Full record incl. `items`, `patient` (age, gender, phone, allergies) and `clinic` (name, address, phone) for printing |
| PUT | `/emr/prescriptions/{id}` | Draft only (409 otherwise). Body: `vitals`, `complaints`, `diagnosis`, `advice`, `follow_up_date`, `items[]` (replaces all lines). Negative vitals → 422 |
| POST | `/emr/prescriptions/{id}/issue` | Draft → issued (locks it) and, if the visit is `in_consult`, completes the appointment. 422 with no medicines |
| POST | `/emr/prescriptions/{id}/cancel` | Body: `reason` (required). Frees the appointment for a replacement Rx |
| GET | `/emr/prescriptions/suggestions?q=&limit=` | Medicine names this clinic prescribed before, most-used first |
| GET | `/emr/patients/{patient_id}/prescriptions` | The patient's prescription history, newest first |

---

*When a new endpoint is added, document it here in the same PR.*
*Owner: The developer adding the endpoint.*
