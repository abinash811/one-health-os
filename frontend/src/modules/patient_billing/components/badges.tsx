import React from 'react';
import { StatusBadge } from '@/components/shared';
import { CHARGE_SOURCE, CHARGE_STATUS, INVOICE_STATUS } from '@/constants/domainConstants';

const SOURCE_STYLES: Record<string, string> = {
  [CHARGE_SOURCE.EMR]: 'bg-blue-50 text-blue-700',
  [CHARGE_SOURCE.PHARMACY]: 'bg-purple-50 text-purple-700',
  [CHARGE_SOURCE.IPD]: 'bg-amber-50 text-amber-700',
  [CHARGE_SOURCE.LAB]: 'bg-gray-100 text-gray-700',
  [CHARGE_SOURCE.MANUAL]: 'bg-gray-100 text-gray-700',
};
export const SOURCE_LABELS: Record<string, string> = {
  [CHARGE_SOURCE.EMR]: 'EMR', [CHARGE_SOURCE.PHARMACY]: 'Pharmacy', [CHARGE_SOURCE.IPD]: 'IPD',
  [CHARGE_SOURCE.LAB]: 'Lab', [CHARGE_SOURCE.MANUAL]: 'Manual',
};

/** Where a charge came from — EMR, Lab, IPD, Manual (Pharmacy mirrors later). */
export function SourceBadge({ source }: { source: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${SOURCE_STYLES[source] || 'bg-gray-100 text-gray-700'}`}
      data-testid={`source-${source}`}>
      {SOURCE_LABELS[source] || source}
    </span>
  );
}

/** An invoice that is issued but not paid reads "Unpaid" — that is what the front desk cares about. */
export function InvoiceBadge({ status }: { status: string }) {
  if (status === INVOICE_STATUS.ISSUED) return <StatusBadge status="unpaid" label="Unpaid" />;
  if (status === INVOICE_STATUS.PART_PAID) return <StatusBadge status="part_paid" />;
  return <StatusBadge status={status} />;
}

export function ChargeBadge({ status }: { status: string }) {
  if (status === CHARGE_STATUS.UNBILLED) return <StatusBadge status="unbilled" label="Unbilled" />;
  if (status === CHARGE_STATUS.INVOICED) return <StatusBadge status="invoiced" label="Invoiced" />;
  return <StatusBadge status={status} />;
}
