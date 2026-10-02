/**
 * domainConstants.js
 *
 * Single source of truth for every status value, enum, and domain string
 * used across PharmaCare frontend.
 *
 * RULE: Never write a magic string for status, type, or mode anywhere in
 * the app. Always import from here. If a value doesn't exist here, add it
 * here first — then use it.
 *
 * This file mirrors the exact values stored in the PostgreSQL database.
 * If the DB value changes, change it here — the entire app updates.
 */

// ─── Bill Status ──────────────────────────────────────────────────────────────
// Stored in bills.status column.
// "draft" is what the DB stores when a bill is parked/held.
// Never write 'draft', 'paid', 'due' as raw strings anywhere else.
export const BILL_STATUS = {
  DRAFT:    'draft',   // Parked / held — not yet settled
  PAID:     'paid',    // Fully paid
  DUE:      'due',     // Partially paid — balance outstanding
  PARTIAL:  'partial', // Alias used in some older records
  REFUNDED: 'refunded',
};

// What the UI calls "Parked" is stored as BILL_STATUS.DRAFT in the DB.
// Use this mapping when building filters so the UI label never has to
// know the DB value.
export const BILL_STATUS_FILTER_MAP = {
  parked: [BILL_STATUS.DRAFT, 'parked'], // match both for safety
  due:    [BILL_STATUS.DUE],
  paid:   [BILL_STATUS.PAID],
};

// Statuses that mean a bill is NOT yet settled.
// Payment method filters (cash, upi) must EXCLUDE these —
// a parked bill is not a completed sale regardless of which
// payment method was pre-selected.
export const UNSETTLED_STATUSES = [BILL_STATUS.DRAFT, 'parked'];

// ─── Payment Methods ──────────────────────────────────────────────────────────
// "Card" and "Credit" were replaced by explicit CREDIT_CARD/DEBIT_CARD Sep
// 24, 2026 (Abinash, direct instruction) — the old flat "Credit" option
// dated from when a bill could carry a running due balance; since due bills
// were removed (Sep 19, 2026) "Credit" only ever meant "paid by credit
// card," so it's now its own explicit method alongside Debit Card instead
// of an ambiguous leftover. 'card'/'credit' can still appear on bills
// created before this change — never rewritten (Manifesto rule 6) — so
// label maps that render historical data keep displaying them.
export const PAYMENT_METHOD = {
  CASH:        'cash',
  UPI:         'upi',
  CREDIT_CARD: 'credit_card',
  DEBIT_CARD:  'debit_card',
  MULTIPLE:    'multiple',
};

export const PAYMENT_METHOD_LABELS = {
  [PAYMENT_METHOD.CASH]: 'Cash',
  [PAYMENT_METHOD.UPI]: 'UPI',
  [PAYMENT_METHOD.CREDIT_CARD]: 'Credit Card',
  [PAYMENT_METHOD.DEBIT_CARD]: 'Debit Card',
  [PAYMENT_METHOD.MULTIPLE]: 'Multiple',
  // Legacy values — no longer selectable, kept so old bills still render a
  // real label instead of a blank/raw string.
  card: 'Card',
  credit: 'Credit',
};

// ─── Purchase Entry — Pack / Unit ──────────────────────────────────────────────
// A purchase line's Qty/PTR/MRP can be typed either per real dispensable
// unit (tablet, ml) or per pack (strip, bottle) — see
// frontend/src/pages/PurchaseNew/utils/packUnitConversion.js for the
// conversion, added Sep 24, 2026 so a pharmacist buying "10 strips at ₹30"
// never has to compute ₹3/tablet by hand.
export const PURCHASE_QTY_MODE = {
  UNIT: 'unit',
  PACK: 'pack',
};

// ─── Purchase Payment Methods ─────────────────────────────────────────────────
// Stored in purchase_payments.payment_method — how a pharmacy pays ITS
// suppliers, a different set from PAYMENT_METHOD above (that's how a
// customer pays the pharmacy). Two independently-built purchase payment
// modals (PurchasesList and PurchaseDetail) each hardcoded their own copy
// of this list before being consolidated into one <PurchasePayModal>.
export const PURCHASE_PAYMENT_METHOD = {
  CASH:          'cash',
  BANK_TRANSFER: 'bank_transfer',
  CHEQUE:        'cheque',
  UPI:           'upi',
};

export const PURCHASE_PAYMENT_METHOD_LABELS = {
  [PURCHASE_PAYMENT_METHOD.CASH]: 'Cash',
  [PURCHASE_PAYMENT_METHOD.BANK_TRANSFER]: 'Bank Transfer',
  [PURCHASE_PAYMENT_METHOD.CHEQUE]: 'Cheque',
  [PURCHASE_PAYMENT_METHOD.UPI]: 'UPI',
};

// ─── Invoice Types ────────────────────────────────────────────────────────────
export const INVOICE_TYPE = {
  SALE:           'SALE',
  PURCHASE:       'PURCHASE',
  SALES_RETURN:   'SALES_RETURN',
  PURCHASE_RETURN:'PURCHASE_RETURN',
};

// ─── Bill Sequence — document types with their own number series ─────────────
// GST requires Sales Invoices and Sales Return credit notes to be numbered as
// separate, gapless sequences — see docs/07_BUSINESS_LOGIC.md.
export const SEQUENCE_DOCUMENT_TYPE = {
  SALES_INVOICE: 'sales_invoice',
  SALES_RETURN:  'sales_return',
};

// ─── Purchase Status ──────────────────────────────────────────────────────────
export const PURCHASE_STATUS = {
  DRAFT:    'draft',
  RECEIVED: 'received',
  PARTIAL:  'partial',
  RETURNED: 'returned',
};

// ─── Schedule Types ───────────────────────────────────────────────────────────
// Drug schedule codes per CDSCO India. H1 requires doctor prescription.
export const DRUG_SCHEDULE = {
  H:  'H',
  H1: 'H1',
  X:  'X',
  G:  'G',
};

// Schedules that require a doctor name before billing
export const SCHEDULE_REQUIRES_DOCTOR = [DRUG_SCHEDULE.H, DRUG_SCHEDULE.H1];

// ─── Customer Types ───────────────────────────────────────────────────────────
export const CUSTOMER_TYPE = {
  REGULAR:     'regular',
  WHOLESALE:   'wholesale',
  INSTITUTION: 'institution',
};

// ─── Report scope toggle (multi-chain Step 4, docs/26_MULTI_CHAIN_SCOPE.md;
// reused Step 6 by the GST report) ─────────────────────────────────────────
export const REPORT_SCOPE = {
  STORE: 'store',
  CHAIN: 'chain',
};

// ─── Stock Movement Types ─────────────────────────────────────────────────────
export const STOCK_MOVEMENT_TYPE = {
  SALE:         'sale',
  PURCHASE:     'purchase',
  RETURN:       'return',
  EXPIRY:       'expiry',
  DAMAGE:       'damage',
  ADJUST:       'adjustment',
  TRANSFER_OUT: 'transfer_out',
  TRANSFER_IN:  'transfer_in',
};

// ─── Sales Return Refund Methods ───────────────────────────────────────────────
// Stored in sales_returns.refund_method. SAME_AS_ORIGINAL is a frontend-only
// convenience default sent to POST /sales-returns — the backend always
// resolves it to one of the concrete REFUND_METHOD values below before
// saving, so a return is never stored with an ambiguous label.
export const REFUND_METHOD = {
  CASH:              'cash',
  UPI:               'upi',
  CREDIT_TO_ACCOUNT: 'credit_to_account',
};
export const REFUND_METHOD_SAME_AS_ORIGINAL = 'same_as_original';

// ─── Purchase Return Reasons ────────────────────────────────────────────────────
// Stored free-text in purchase_returns.return_reason (String(50), no DB enum) —
// found Sep 15, 2026 (product-review) sending only ever the literal "return"
// regardless of what actually happened, since the frontend had no reason field
// at all. A standard, small set for what a pharmacist actually returns goods to
// a distributor for — not the full 11-item list from the original use-case spec,
// which mixed in sales-return-shaped reasons that don't apply to a purchase
// going back to a supplier.
export const PURCHASE_RETURN_REASON = {
  DAMAGED:         'damaged',
  EXPIRED:         'expired',
  NEAR_EXPIRY:     'near_expiry',
  WRONG_ITEM:      'wrong_item',
  EXCESS_STOCK:    'excess_stock',
  QUALITY_ISSUE:   'quality_issue',
  ORDER_CANCELLED: 'order_cancelled',
  OTHER:           'other',
};
export const PURCHASE_RETURN_REASON_LABELS = {
  [PURCHASE_RETURN_REASON.DAMAGED]:         'Damaged in transit',
  [PURCHASE_RETURN_REASON.EXPIRED]:         'Expired',
  [PURCHASE_RETURN_REASON.NEAR_EXPIRY]:     'Near expiry',
  [PURCHASE_RETURN_REASON.WRONG_ITEM]:      'Wrong item shipped',
  [PURCHASE_RETURN_REASON.EXCESS_STOCK]:    'Excess stock',
  [PURCHASE_RETURN_REASON.QUALITY_ISSUE]:   'Quality issue',
  [PURCHASE_RETURN_REASON.ORDER_CANCELLED]: 'Order cancelled',
  [PURCHASE_RETURN_REASON.OTHER]:           'Other',
};

// ─── Purchase Return Settlement Type ───────────────────────────────────────────
// Stored in purchase_returns.payment_type — the create form's dropdown always
// sent this, but nothing stored or read it back until Sep 16, 2026
// (product-review PR12); the Returns list's Cash/UPI/Credit filter pills were
// silently broken the whole time as a result (always compared against
// `undefined`). Record-keeping only — does not gate how the return's value is
// netted against the supplier's outstanding balance (see the model comment on
// PurchaseReturn.payment_type for why that's a separate, still-open question).
export const PURCHASE_RETURN_PAYMENT_TYPE_LABELS = {
  cash: 'Cash',
  upi: 'UPI',
  credit: 'Credit',
  adjust_outstanding: 'Adjust Against Outstanding',
};

// ─── User Roles ───────────────────────────────────────────────────────────────
// Mirrors backend/constants.py::DEFAULT_ROLES names exactly. A new pharmacy
// (created at signup — see routers/auth.py) always gets all four; the
// signing-up user is always ROLE.ADMIN for their own pharmacy.
export const USER_ROLE = {
  ADMIN:           'admin',
  MANAGER:         'manager',
  CASHIER:         'cashier',
  INVENTORY_STAFF: 'inventory_staff',
  RECEPTIONIST:    'receptionist',
  DOCTOR:          'doctor',
};

// ── EMR (backend/modules/emr/constants.py — keep in sync) ────────────────────
export const APPOINTMENT_STATUS = {
  BOOKED:     'booked',
  CHECKED_IN: 'checked_in',
  IN_CONSULT: 'in_consult',
  COMPLETED:  'completed',
  CANCELLED:  'cancelled',
  NO_SHOW:    'no_show',
};

export const APPOINTMENT_TYPE = {
  SCHEDULED: 'scheduled',
  WALK_IN:   'walk_in',
};

// 0 = Monday … 6 = Sunday, same as the backend's `weekday`.
export const WEEKDAY_LABELS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
