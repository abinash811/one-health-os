import React from 'react';
import { DataCard } from '@/components/shared';
import { APPOINTMENT_STATUS } from '@/constants/domainConstants';
import { rupeesLabel } from '@/modules/patient_billing/money';
import type { DaySummary } from '@/modules/patient_billing/types';
import type { EmrAppointment } from '../types';

export interface QueueSummaryProps {
  rows: EmrAppointment[];
  /** Today's money collected across counters; null when the user can't see billing. */
  collected: DaySummary | null;
}

const Stat = ({ label, value, sub, tone = '', testId }: { label: string; value: string; sub?: string; tone?: string; testId: string }) => (
  <DataCard noPadding={false} className={tone}>
    <p className="text-xs font-bold uppercase tracking-wide text-gray-500">{label}</p>
    <p className="text-2xl font-bold text-gray-900 mt-1" data-testid={testId}>{value}</p>
    {sub && <p className="text-xs text-gray-500">{sub}</p>}
  </DataCard>
);

/** The day at a glance: who is waiting, who is in, who is done, and money collected. */
export default function QueueSummary({ rows, collected }: QueueSummaryProps) {
  const n = (s: string) => rows.filter((r) => r.status === s).length;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4" data-testid="queue-summary">
      <Stat label="Waiting" value={String(n(APPOINTMENT_STATUS.CHECKED_IN))} testId="stat-waiting" />
      <Stat label="In consult" value={String(n(APPOINTMENT_STATUS.IN_CONSULT))} testId="stat-in-consult" />
      <Stat label="Done" value={String(n(APPOINTMENT_STATUS.COMPLETED))} testId="stat-done" />
      {collected && (
        <Stat label="Collected today" value={rupeesLabel(collected.collected_paise)} testId="stat-collected"
          sub={`${collected.receipts} receipt${collected.receipts === 1 ? '' : 's'}`} tone="border-brand bg-brand-subtle" />
      )}
    </div>
  );
}
