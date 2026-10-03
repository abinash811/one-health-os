import React, { useState } from 'react';
import { toast } from 'sonner';
import { DataCard, AppButton, ErrorState, PaginationBar } from '@/components/shared';
import { apiUrl } from '@/constants/api';
import { today } from '@/utils/dates';
import { exportToExcel } from '@/utils/excelExport';
import { MODE_LABELS } from '../money';
import { pageBarProps, useQuery } from '../useQuery';
import ReceiptsTable from './ReceiptsTable';
import type { PagedResponse, PbPayment } from '../types';

/** Every receipt, newest first, for one day or for all days. */
export default function ReceiptsTab() {
  const [date, setDate] = useState<string>(today());
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const res = useQuery<PagedResponse<PbPayment>>(apiUrl.pbPayments({ date: date || undefined, page, page_size: 20 }), tick);
  const rows = res.data?.data || [];

  const exportRows = () => {
    try {
      exportToExcel(rows.map((p) => ({
        Receipt: p.receipt_number, Date: p.paid_on, Patient: p.patient_name || '', UHID: p.patient_uhid || '',
        Invoice: p.invoice_number || '', Mode: MODE_LABELS[p.mode] || p.mode, Reference: p.reference || '',
        'Amount (₹)': p.amount_paise / 100 })), 'receipts', { sheetName: 'Receipts' });
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div data-testid="receipts-tab">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input type="date" value={date} onChange={(e) => { setDate(e.target.value); setPage(1); }} aria-label="Receipt date"
          data-testid="receipts-date" className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand" />
        {date !== today() && <AppButton variant="ghost" size="sm" onClick={() => { setDate(today()); setPage(1); }}>Today</AppButton>}
        {date && <AppButton variant="ghost" size="sm" onClick={() => { setDate(''); setPage(1); }} data-testid="receipts-all-days">All days</AppButton>}
        <AppButton variant="outline" className="ml-auto" onClick={exportRows} disabled={!rows.length} data-testid="export-receipts">Export</AppButton>
      </div>
      <DataCard noPadding>
        {res.error ? <ErrorState message={res.error} onRetry={() => setTick((t) => t + 1)} />
          : <ReceiptsTable rows={rows} loading={res.loading} emptyText={date ? 'No payments were collected on this day.' : undefined} />}
        <PaginationBar {...pageBarProps(page, setPage, res.data?.pagination)} />
      </DataCard>
    </div>
  );
}
