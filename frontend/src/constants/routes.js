/**
 * PHARMACARE — Route Constants
 *
 * Single source of truth for every URL path in the app.
 * Use these instead of hardcoding strings in navigate() / <Link to=...>.
 *
 * Two layers:
 *   ROUTES       — static path strings (use in <Route path=...>)
 *   routeTo.*()  — helper functions that build dynamic URLs
 *
 * Usage:
 *   import { ROUTES, routeTo } from '@/constants/routes';
 *
 *   // Static
 *   navigate(ROUTES.BILLING.LIST)
 *   <Route path={ROUTES.BILLING.NEW} element={...} />
 *
 *   // Dynamic
 *   navigate(routeTo.bill(bill.id))
 *   navigate(routeTo.purchaseEdit(id))
 */

// ── Route Path Definitions ────────────────────────────────────────────────────

export const ROUTES = {

  // Auth
  AUTH: {
    LOGIN: '/',
  },

  // Top-level
  DASHBOARD: '/dashboard',

  // Billing / Sales
  BILLING: {
    LIST:         '/billing',
    NEW:          '/billing/new',
    CREATE:       '/billing/create',
    EDIT:         '/billing/edit/:id',
    DETAIL:       '/billing/:id',
  },

  // Sales Returns
  SALES_RETURNS: {
    LIST:         '/billing/returns',
    NEW:          '/billing/returns/new',
    EDIT:         '/billing/returns/edit/:id',
    DETAIL:       '/billing/returns/:id',
  },

  // Patient Billing (clinic module) — printable pages render outside the app shell
  PATIENT_BILLING: {
    HOME:     '/patient-billing',
    PENDING:  '/patient-billing/pending',
    INVOICES: '/patient-billing/invoices',
    RECEIPTS: '/patient-billing/receipts',
    CLOSING:  '/patient-billing/closing',
    ACCOUNT:  (patientId) => `/patient-billing/accounts/${patientId}`,
    INVOICE_PRINT: (invoiceId) => `/patient-billing/invoices/${invoiceId}/print`,
  },

  // EMR (clinic module)
  EMR: {
    APPOINTMENTS: '/emr/appointments',
    PATIENTS:     '/emr/patients',
    PATIENT:      (id) => `/emr/patients/${id}`,
    SCHEDULES:    '/emr/schedules',
    SETTINGS:     '/emr/settings',
    CONSULT:      (appointmentId) => `/emr/consult/${appointmentId}`,
    RX_PRINT:     (rxId) => `/emr/prescriptions/${rxId}/print`,
  },

  // Inventory
  INVENTORY: {
    LIST:         '/inventory',
    PRODUCT:      '/inventory/product/:sku',
    EDIT:         '/inventory/edit/:sku',
  },

  // Purchases
  PURCHASES: {
    LIST:         '/purchases',
    CREATE:       '/purchases/create',
    EDIT:         '/purchases/edit/:id',
    DETAIL:       '/purchases/:id',
  },

  // Purchase Returns
  PURCHASE_RETURNS: {
    LIST:         '/purchases/returns',
    CREATE:       '/purchases/returns/create',
    DETAIL:       '/purchases/returns/:id',
  },

  // Other modules
  CUSTOMERS:  '/customers',
  SUPPLIERS:  '/suppliers',

  REPORTS: {
    MAIN:         '/reports',
    GST:          '/reports/gst',
  },

  SETTINGS:   '/settings',
  USERS:      '/users',
  ROLES:      '/roles',
};


// ── Dynamic URL Builders ──────────────────────────────────────────────────────
// These replace template-literal navigation calls scattered through pages.

export const routeTo = {

  /** /billing/:id — view or edit a bill */
  bill: (id) => `/billing/${id}`,

  /** /billing/edit/:id — edit an existing draft bill */
  billEdit: (id) => `/billing/edit/${id}`,

  /** /billing/returns/:id — sales return detail */
  salesReturn: (id) => `/billing/returns/${id}`,

  /** /billing/returns/edit/:id — edit a sales return (financial adj.) */
  salesReturnEdit: (id) => `/billing/returns/edit/${id}`,

  /** /billing/returns/new?billId=<id> — create return from a bill */
  salesReturnNew: (billId) =>
    billId ? `/billing/returns/new?billId=${billId}` : '/billing/returns/new',

  /** /inventory/product/:sku — product detail */
  product: (sku) => `/inventory/product/${sku}`,

  /** /inventory/edit/:sku — edit product */
  productEdit: (sku) => `/inventory/edit/${sku}`,

  /** /purchases/:id — purchase detail */
  purchase: (id) => `/purchases/${id}`,

  /** /purchases/edit/:id?type=purchase — edit a purchase */
  purchaseEdit: (id) => `/purchases/edit/${id}?type=purchase`,

  /** /purchases/returns/:id — purchase return detail */
  purchaseReturn: (id) => `/purchases/returns/${id}`,

  /** /purchases/returns/create?purchase_id=<id> — create return from purchase */
  purchaseReturnCreate: (purchaseId) =>
    purchaseId
      ? `/purchases/returns/create?purchase_id=${purchaseId}`
      : '/purchases/returns/create',
};
