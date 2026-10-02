import React from 'react';

const STATUS_STYLES: Record<string, string> = {
  paid: 'bg-green-50 text-green-700',
  cash: 'bg-green-50 text-green-700',
  completed: 'bg-green-50 text-green-700',
  active: 'bg-green-50 text-green-700',
  confirmed: 'bg-green-50 text-green-700',
  due: 'bg-amber-50 text-amber-700',
  unpaid: 'bg-amber-50 text-amber-700',
  overdue: 'bg-red-50 text-red-700',
  cancelled: 'bg-red-50 text-red-700',
  inactive: 'bg-red-50 text-red-700',
  rejected: 'bg-red-50 text-red-700',
  partial: 'bg-amber-50 text-amber-700',
  parked: 'bg-amber-50 text-amber-700',
  pending: 'bg-amber-50 text-amber-700',
  draft: 'bg-amber-50 text-amber-700',
  upi: 'bg-blue-50 text-blue-700',
  credit_card: 'bg-purple-50 text-purple-700',
  debit_card: 'bg-purple-50 text-purple-700',
  // Legacy — bills created before the Sep 24, 2026 Credit Card/Debit Card split.
  credit: 'bg-purple-50 text-purple-700',
  card: 'bg-purple-50 text-purple-700',
  multiple: 'bg-blue-50 text-blue-700',
  adjusted: 'bg-purple-50 text-purple-700',
  same_as_original: 'bg-gray-100 text-gray-700',
  credit_to_account: 'bg-purple-50 text-purple-700',
  regular: 'bg-blue-50 text-blue-700',
  wholesale: 'bg-purple-50 text-purple-700',
  institution: 'bg-green-50 text-green-700',
  // Inventory stock-health statuses (see docs/06_COMPONENTS.md)
  healthy: 'bg-green-50 text-green-700',
  low_stock: 'bg-amber-50 text-amber-700',
  near_expiry: 'bg-amber-50 text-amber-700',
  out_of_stock: 'bg-red-50 text-red-700',
  expired: 'bg-red-50 text-red-700',
  // Purchase return credit-status (see docs/23_PURCHASES_ACCEPTANCE_SPEC.md) —
  // pending/rejected already covered above.
  partially_credited: 'bg-amber-50 text-amber-700',
  fully_credited: 'bg-green-50 text-green-700',
  // EMR appointment statuses (completed/cancelled already covered above)
  issued: 'bg-green-50 text-green-700',
  booked: 'bg-blue-50 text-blue-700',
  checked_in: 'bg-amber-50 text-amber-700',
  in_consult: 'bg-purple-50 text-purple-700',
  default: 'bg-gray-100 text-gray-700',
};

// Dot indicator colors, only used when <StatusBadge dot /> is passed.
const DOT_COLORS: Record<string, string> = {
  healthy: 'bg-green-500',
  low_stock: 'bg-amber-500',
  near_expiry: 'bg-amber-500',
  out_of_stock: 'bg-red-500',
  expired: 'bg-red-500',
};

const LABEL_MAPPINGS: Record<string, string> = {
  same_as_original: 'Same as Original',
  credit_to_account: 'Credit to Account',
  adjust_outstanding: 'Adjusted',
  low_stock: 'Low Stock',
  near_expiry: 'Near Expiry',
  out_of_stock: 'Out of Stock',
  partially_credited: 'Partially Credited',
  fully_credited: 'Fully Credited',
  checked_in: 'Checked In',
  in_consult: 'In Consult',
  no_show: 'No Show',
  multiple: 'Multi',
  credit_card: 'Credit Card',
  debit_card: 'Debit Card',
};

export interface StatusBadgeProps {
  status?: string | null;
  label?: string;
  fallback?: string;
  className?: string;
  /** Show a small colored dot before the label (used by stock-health badges). */
  dot?: boolean;
}

export function StatusBadge({ status, label, fallback = '-', className = '', dot = false }: StatusBadgeProps) {
  if (!status || status === 'NaN' || !status.trim()) {
    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_STYLES.default} ${className}`}>
        {fallback}
      </span>
    );
  }

  const normalizedStatus = status.toLowerCase().trim();
  const styleClass = STATUS_STYLES[normalizedStatus] ?? STATUS_STYLES.default;
  const dotColor = DOT_COLORS[normalizedStatus];
  const displayLabel = label
    ?? LABEL_MAPPINGS[normalizedStatus]
    ?? (status.charAt(0).toUpperCase() + status.slice(1).toLowerCase());

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${styleClass} ${className}`}
      data-testid={`status-badge-${normalizedStatus}`}
    >
      {dot && dotColor && <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />}
      {displayLabel}
    </span>
  );
}

export interface CustomerTypeBadgeProps {
  type?: string | null;
}

export function CustomerTypeBadge({ type }: CustomerTypeBadgeProps) {
  const safeType = type?.trim() || 'regular';
  return <StatusBadge status={safeType} fallback="Regular" />;
}

export interface PaymentStatusBadgeProps {
  status?: string | null;
  paymentMethod?: string | null;
}

export function PaymentStatusBadge({ status, paymentMethod }: PaymentStatusBadgeProps) {
  if (status === 'parked' || status === 'draft') return <StatusBadge status="parked" label="Parked" />;
  if (status === 'due' || status === 'unpaid')   return <StatusBadge status="due"    label="Due" />;
  if (status === 'partial')                       return <StatusBadge status="partial" label="Partial" />;
  if (status === 'paid') {
    const method = paymentMethod?.toLowerCase();
    if (method === 'upi')                  return <StatusBadge status="upi"   label="UPI" />;
    if (method === 'credit_card')          return <StatusBadge status="credit_card" label="Credit Card" />;
    if (method === 'debit_card')           return <StatusBadge status="debit_card" label="Debit Card" />;
    // Legacy values from before the Sep 24, 2026 Credit Card/Debit Card
    // split — still shown as-is on bills created before that change
    // (Manifesto rule 6: never rewritten).
    if (method === 'card' || method === 'cc/dc') return <StatusBadge status="card" label="Card" />;
    if (method === 'credit')               return <StatusBadge status="credit" label="Credit" />;
    return <StatusBadge status="cash" label="Cash" />;
  }
  return <StatusBadge status={status ?? 'pending'} />;
}
