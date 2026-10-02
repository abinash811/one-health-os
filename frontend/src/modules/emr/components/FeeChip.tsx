import React from 'react';
import { StatusBadge } from '@/components/shared';
import { FEE_STATUS } from '@/constants/domainConstants';
import { MODE_LABELS, rupeesLabel } from '@/modules/patient_billing/money';
import type { EmrFee } from '../types';

/** The visit's consultation fee at a glance: "₹500 · Unpaid", "₹500 · Part-paid", "₹500 · Paid (UPI)". */
export default function FeeChip({ fee }: { fee?: EmrFee | null }) {
  if (!fee) return <span className="text-gray-400" data-testid="fee-none">—</span>;
  const amount = rupeesLabel(fee.amount_paise);
  const label = fee.status === FEE_STATUS.PAID
    ? `${amount} · Paid${fee.mode ? ` (${MODE_LABELS[fee.mode] || fee.mode})` : ''}`
    : fee.status === FEE_STATUS.PART_PAID ? `${amount} · Part-paid` : `${amount} · Unpaid`;
  return <span data-testid="fee-chip"><StatusBadge status={fee.status} label={label} /></span>;
}
