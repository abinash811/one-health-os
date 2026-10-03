import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { FileText, Printer, XCircle } from 'lucide-react';
import { DataCard, AppButton, EmptyState, ErrorState, FilterPills, MoreMenu, PaginationBar, SearchInput, TableSkeleton } from '@/components/shared';
import { apiUrl } from '@/constants/api';
import { INVOICE_STATUS, BILLING_COUNTER } from '@/constants/domainConstants';
import { ROUTES } from '@/constants/routes';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import { exportToExcel } from '@/utils/excelExport';
import { formatDate } from '@/utils/dates';
import { rupeesLabel } from '../money';
import { pageBarProps, useQuery } from '../useQuery';
import { InvoiceBadge } from './badges';
import CancelInvoiceDialog from './CancelInvoiceDialog';
import CollectPaymentDialog from './CollectPaymentDialog';
import type { PagedResponse, PbInvoice } from '../types';

const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';
const FILTERS = [
  { key: 'all', label: 'All' }, { key: INVOICE_STATUS.ISSUED, label: 'Unpaid' },
  { key: INVOICE_STATUS.PART_PAID, label: 'Part-paid' }, { key: INVOICE_STATUS.PAID, label: 'Paid' },
  { key: INVOICE_STATUS.CANCELLED, label: 'Cancelled' },
];
const COUNTER_LABELS: Record<string, string> = {
  [BILLING_COUNTER.FRONT_DESK]: 'Front desk', [BILLING_COUNTER.BILLING_DESK]: 'Billing desk',
  [BILLING_COUNTER.LAB]: 'Lab', [BILLING_COUNTER.IPD]: 'IPD',
};

/** Every invoice, newest first — find one, print it, take the rest of its payment, or cancel it. */
export default function AllBillsTab() {
  const navigate = useNavigate();
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const [paying, setPaying] = useState<PbInvoice | null>(null);
  const [cancelling, setCancelling] = useState<PbInvoice | null>(null);
  const applySearch = useDebouncedCallback((v: string) => { setQuery(v); setPage(1); }, 300);
  const refresh = () => setTick((t) => t + 1);

  const res = useQuery<PagedResponse<PbInvoice>>(apiUrl.pbInvoices({
    status: status === 'all' ? undefined : status, search: query || undefined, page, page_size: 20 }), tick);
  const rows = res.data?.data || [];

  const exportRows = () => {
    try {
      exportToExcel(rows.map((i) => ({
        Invoice: i.invoice_number, Date: formatDate(i.created_at), Patient: i.patient_name, UHID: i.patient_uhid || '',
        'Net (₹)': i.net_paise / 100, 'Paid (₹)': i.paid_paise / 100, 'Balance (₹)': i.balance_paise / 100,
        Status: i.status, Counter: COUNTER_LABELS[i.counter] || i.counter })), 'invoices', { sheetName: 'Invoices' });
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div data-testid="all-bills-tab">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <FilterPills options={FILTERS} active={status} onChange={(k) => { setStatus(k); setPage(1); }} />
        <div className="ml-auto flex items-center gap-2">
          <SearchInput value={search} onChange={(v) => { setSearch(v); applySearch(v); }} placeholder="Search invoice, patient or UHID" className="w-72" />
          <AppButton variant="outline" onClick={exportRows} disabled={!rows.length} data-testid="export-invoices">Export</AppButton>
        </div>
      </div>
      <DataCard noPadding>
        {res.error ? <ErrorState message={res.error} onRetry={refresh} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="invoices-table">
              <thead className="bg-gray-50 border-b"><tr>
                <th className={TH}>Invoice</th><th className={TH}>Date</th><th className={TH}>Patient</th>
                <th className={`${TH} text-right`}>Net</th><th className={`${TH} text-right`}>Paid</th><th className={`${TH} text-right`}>Balance</th>
                <th className={TH}>Status</th><th className={TH}>Counter</th><th className={`${TH} text-right`}>Actions</th>
              </tr></thead>
              <tbody className="divide-y">
                {res.loading ? <tr><td colSpan={9} className="p-0"><TableSkeleton rows={6} columns={9} /></td></tr>
                  : rows.length === 0 ? (
                    <tr><td colSpan={9}><EmptyState icon={FileText} title="No bills found"
                      description={query || status !== 'all' ? 'Try a different filter or search.' : 'Invoices appear here once charges are billed.'} /></td></tr>
                  ) : rows.map((i) => (
                    <tr key={i.id} className="hover:bg-brand-tint transition-colors" data-testid={`invoice-row-${i.id}`}>
                      <td className="px-4 py-3 font-mono font-semibold whitespace-nowrap">{i.invoice_number}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{formatDate(i.created_at)}</td>
                      <td className="px-4 py-3"><p className="font-medium text-gray-900">{i.patient_name}</p>
                        <p className="text-xs font-mono text-gray-500">{i.patient_uhid || ''}</p></td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">{rupeesLabel(i.net_paise)}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">{rupeesLabel(i.paid_paise)}</td>
                      <td className="px-4 py-3 text-right font-semibold whitespace-nowrap">{rupeesLabel(i.balance_paise)}</td>
                      <td className="px-4 py-3"><InvoiceBadge status={i.status} /></td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{COUNTER_LABELS[i.counter] || i.counter}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap"><div className="flex items-center justify-end gap-1">
                        {i.balance_paise > 0 && i.status !== INVOICE_STATUS.CANCELLED && (
                          <AppButton size="sm" onClick={() => setPaying(i)} data-testid={`pay-${i.id}`}>Pay {rupeesLabel(i.balance_paise)}</AppButton>
                        )}
                        <MoreMenu testId={`invoice-more-${i.id}`} items={[
                          { icon: <Printer className="w-4 h-4" />, label: 'View / print', action: () => navigate(ROUTES.PATIENT_BILLING.INVOICE_PRINT(i.id)) },
                          i.paid_paise === 0 && i.status === INVOICE_STATUS.ISSUED && {
                            icon: <XCircle className="w-4 h-4" />, label: 'Cancel invoice', action: () => setCancelling(i) },
                        ]} />
                      </div></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationBar {...pageBarProps(page, setPage, res.data?.pagination)} />
      </DataCard>
      {paying && (
        <CollectPaymentDialog open patientId={paying.patient_id} patientName={paying.patient_name} charges={[]}
          existingInvoice={{ id: paying.id, invoice_number: paying.invoice_number, balance_paise: paying.balance_paise }}
          onClose={() => setPaying(null)} onCollected={refresh} />
      )}
      <CancelInvoiceDialog invoice={cancelling} onClose={() => setCancelling(null)} onCancelled={refresh} />
    </div>
  );
}
