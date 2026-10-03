import React, { useState } from 'react';
import { DataCard, AppButton, ErrorState } from '@/components/shared';
import { apiUrl } from '@/constants/api';
import { BILLING_COUNTER, PAYMENT_MODE } from '@/constants/domainConstants';
import { today } from '@/utils/dates';
import { MODE_LABELS, rupeesLabel } from '../money';
import { useQuery } from '../useQuery';
import ReceiptsTable from './ReceiptsTable';
import type { DaySummary, PagedResponse, PbPayment } from '../types';

const COUNTERS: [string, string][] = [
  [BILLING_COUNTER.FRONT_DESK, 'Front desk'], [BILLING_COUNTER.BILLING_DESK, 'Billing desk'],
  [BILLING_COUNTER.LAB, 'Lab'], [BILLING_COUNTER.IPD, 'IPD'],
];

const Stat = ({ label, value, sub, tone = '', testId }: { label: string; value: string; sub?: string; tone?: string; testId: string }) => (
  <DataCard noPadding={false} className={tone}>
    <p className="text-xs font-bold uppercase tracking-wide text-gray-500">{label}</p>
    <p className="text-2xl font-bold text-gray-900 mt-1" data-testid={testId}>{value}</p>
    {sub && <p className="text-xs text-gray-500">{sub}</p>}
  </DataCard>
);

/** A day's collections by payment mode and by counter, with the receipts behind them. */
export default function DayClosingTab() {
  const [date, setDate] = useState<string>(today());
  const [tick, setTick] = useState(0);
  const summary = useQuery<DaySummary>(apiUrl.pbSummaryToday({ date }), tick);
  const receipts = useQuery<PagedResponse<PbPayment>>(apiUrl.pbPayments({ date, page: 1, page_size: 100 }), tick);
  const s = summary.data;
  const money = (paise?: number) => (s ? rupeesLabel(paise ?? 0) : '—');

  return (
    <div data-testid="day-closing-tab">
      <div className="flex items-center gap-3 mb-4">
        <input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} aria-label="Closing date"
          data-testid="closing-date" className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand" />
        {date !== today() && <AppButton variant="ghost" size="sm" onClick={() => setDate(today())}>Today</AppButton>}
      </div>
      {summary.error ? <DataCard><ErrorState message={summary.error} onRetry={() => setTick((t) => t + 1)} /></DataCard> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
            <Stat label="Total collected" value={money(s?.collected_paise)} tone="border-brand bg-brand-subtle" testId="closing-total"
              sub={`${s?.receipts ?? 0} receipt${s?.receipts === 1 ? '' : 's'}`} />
            {Object.values(PAYMENT_MODE).map((m) => (
              <Stat key={m} label={m === PAYMENT_MODE.CASH ? 'Cash — in the drawer' : MODE_LABELS[m]} value={money(s?.by_mode[m])}
                testId={`closing-${m}`} />
            ))}
          </div>
          <DataCard noPadding={false} className="mb-4">
            <p className="text-xs font-bold uppercase tracking-wide text-gray-500 mb-2">By counter</p>
            <ul className="grid grid-cols-2 lg:grid-cols-4 gap-x-10 gap-y-2 text-sm" data-testid="closing-counters">
              {COUNTERS.map(([key, label]) => (
                <li key={key} className="flex justify-between"><span className="text-gray-600">{label}</span>
                  <span className="font-semibold" data-testid={`closing-counter-${key}`}>{money(s?.by_counter[key])}</span></li>
              ))}
            </ul>
          </DataCard>
          <DataCard noPadding>
            <div className="px-4 py-3 border-b"><span className="text-xs font-bold uppercase tracking-wide text-gray-500">Receipts on this day</span></div>
            <ReceiptsTable rows={receipts.data?.data || []} loading={receipts.loading} emptyText="No payments were collected on this day." />
          </DataCard>
        </>
      )}
    </div>
  );
}
