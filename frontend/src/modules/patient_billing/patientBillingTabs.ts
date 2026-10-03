/** Tab bar for the billing desk — one definition so keys and routes can't drift apart (same as emrTabs.ts). */
import { ROUTES } from '@/constants/routes';

export const BILLING_TABS = [
  { key: 'pending',  label: 'Pending' },
  { key: 'invoices', label: 'All bills' },
  { key: 'receipts', label: 'Receipts' },
  { key: 'closing',  label: 'Day closing' },
];

const TAB_ROUTES: Record<string, string> = {
  pending:  ROUTES.PATIENT_BILLING.PENDING,
  invoices: ROUTES.PATIENT_BILLING.INVOICES,
  receipts: ROUTES.PATIENT_BILLING.RECEIPTS,
  closing:  ROUTES.PATIENT_BILLING.CLOSING,
};

export const billingTabRoute = (key: string): string => TAB_ROUTES[key] || ROUTES.PATIENT_BILLING.PENDING;
