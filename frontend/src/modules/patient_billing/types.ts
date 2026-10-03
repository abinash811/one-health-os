// Shapes returned by backend/modules/patient_billing/routers (docs/10_API.md → Patient Billing).

export interface PbInvoiceLine {
  charge_id: string;
  description: string;
  quantity: number;
  unit_price_paise: number;
  total_paise: number;
  source_module: string;
  source_ref: string | null;
}

export interface PbPayment {
  id: string;
  patient_id: string;
  invoice_id: string;
  invoice_number: string | null;
  patient_name?: string | null;
  patient_uhid?: string | null;
  amount_paise: number;
  mode: string;
  reference: string | null;
  receipt_number: string;
  paid_on: string;
  created_at: string | null;
}

export interface PbInvoice {
  id: string;
  patient_id: string;
  patient_name: string;
  patient_uhid: string | null;
  invoice_number: string;
  counter: string;
  status: string;
  gross_paise: number;
  discount_paise: number;
  net_paise: number;
  paid_paise: number;
  balance_paise: number;
  lines: PbInvoiceLine[];
  cancel_reason: string | null;
  created_at: string | null;
  payments?: PbPayment[];
}

export interface DaySummary {
  date: string;
  collected_paise: number;
  receipts: number;
  by_mode: Record<string, number>;
  by_counter: Record<string, number>;
}

export interface PbCharge {
  id: string;
  patient_id: string;
  patient_name: string;
  patient_uhid: string | null;
  source_module: string;
  source_ref: string | null;
  description: string;
  quantity: number;
  unit_price_paise: number;
  total_paise: number;
  status: string;
  invoice_id: string | null;
  void_reason: string | null;
  created_at: string | null;
}

/** One row of the billing desk's account list. */
export interface PendingAccount {
  patient_id: string;
  patient_name: string;
  patient_uhid: string | null;
  not_invoiced_paise: number;
  invoiced_unpaid_paise: number;
  balance_paise: number;
  has_part_paid: boolean;
  sources: string[];
  last_activity: string | null;
}

export interface AccountTotals {
  balance_paise: number;
  not_invoiced_paise: number;
  invoiced_unpaid_paise: number;
  patients: number;
}

export interface PagedResponse<T> {
  data: T[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number; has_next: boolean; has_prev: boolean };
}

/** One patient's complete bill. */
export interface AccountDetail {
  patient: { id: string; name: string; uhid: string | null };
  totals: {
    total_charges_paise: number; paid_paise: number; not_invoiced_paise: number;
    invoiced_unpaid_paise: number; balance_paise: number;
  };
  charges: PbCharge[];
  invoices: PbInvoice[];
  payments: PbPayment[];
}
