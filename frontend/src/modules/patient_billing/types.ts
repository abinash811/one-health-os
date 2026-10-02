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
