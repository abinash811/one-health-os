import { formatCurrency, toRupees } from '@/utils/currency';

/** ₹500 for whole rupees, ₹500.50 otherwise — display only; amounts stay integer paise everywhere else. */
export const rupeesLabel = (paise: number): string => {
  const r = toRupees(paise);
  return formatCurrency(r, { decimals: Number.isInteger(r) ? 0 : 2 });
};

export const MODE_LABELS: Record<string, string> = { cash: 'Cash', upi: 'UPI', card: 'Card' };
