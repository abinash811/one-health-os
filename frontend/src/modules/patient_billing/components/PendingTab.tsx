import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Receipt } from 'lucide-react';
import { DataCard, AppButton, EmptyState, ErrorState, FilterPills, PaginationBar, SearchInput, TableSkeleton } from '@/components/shared';
import { apiUrl } from '@/constants/api';
import { ACCOUNT_FILTER, CHARGE_SOURCE } from '@/constants/domainConstants';
import { ROUTES } from '@/constants/routes';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import { exportToExcel } from '@/utils/excelExport';
import { formatDate } from '@/utils/dates';
import { rupeesLabel } from '../money';
import { pageBarProps, useQuery } from '../useQuery';
import { SourceBadge, SOURCE_LABELS } from './badges';
import { useCollect } from './useCollect';
import type { AccountTotals, DaySummary, PagedResponse, PendingAccount } from '../types';

const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';
const FILTERS = [
  { key: ACCOUNT_FILTER.PENDING, label: 'All pending' },
  { key: ACCOUNT_FILTER.NOT_INVOICED, label: 'Not invoiced' },
  { key: ACCOUNT_FILTER.INVOICED_UNPAID, label: 'Invoiced, unpaid' },
  { key: ACCOUNT_FILTER.PART_PAID, label: 'Part-paid' },
];
const SOURCES = [{ key: 'all', label: 'All' },
  ...[CHARGE_SOURCE.EMR, CHARGE_SOURCE.LAB, CHARGE_SOURCE.IPD, CHARGE_SOURCE.MANUAL].map((s) => ({ key: s, label: SOURCE_LABELS[s] }))];

type AccountsResponse = PagedResponse<PendingAccount> & { totals: AccountTotals };

const Stat = ({ label, value, sub, tone = '', testId }: { label: string; value: string; sub: string; tone?: string; testId: string }) => (
  <DataCard noPadding={false} className={tone}>
    <p className="text-xs font-bold uppercase tracking-wide text-gray-500">{label}</p>
    <p className="text-2xl font-bold text-gray-900 mt-1" data-testid={testId}>{value}</p>
    <p className="text-xs text-gray-500">{sub}</p>
  </DataCard>
);

/** The billing desk's list: everyone who owes money, what for, and a Collect button. */
export default function PendingTab() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<string>(ACCOUNT_FILTER.PENDING);
  const [source, setSource] = useState('all');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const applySearch = useDebouncedCallback((v: string) => { setQuery(v); setPage(1); }, 300);
  const refresh = () => setTick((t) => t + 1);
  const { start, dialog, busyId } = useCollect(refresh);

  const list = useQuery<AccountsResponse>(apiUrl.pbAccounts({
    status: filter, source: source === 'all' ? undefined : source, search: query || undefined, page, page_size: 20 }), tick);
  const stats = useQuery<AccountsResponse>(apiUrl.pbAccounts({ status: ACCOUNT_FILTER.PENDING, page_size: 1 }), tick);
  const today = useQuery<DaySummary>(apiUrl.pbSummaryToday(), tick);
  const rows = list.data?.data || [];
  const t = stats.data?.totals;

  const exportRows = () => {
    try {
      exportToExcel(rows.map((r) => ({
        Patient: r.patient_name, UHID: r.patient_uhid || '', 'Not invoiced (₹)': r.not_invoiced_paise / 100,
        'Invoiced, unpaid (₹)': r.invoiced_unpaid_paise / 100, 'Balance (₹)': r.balance_paise / 100,
        'Charges from': r.sources.map((s) => SOURCE_LABELS[s] || s).join(', '),
      })), 'pending-bills', { sheetName: 'Pending' });
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div data-testid="pending-tab">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <Stat label="Total pending" value={t ? rupeesLabel(t.balance_paise) : '—'} sub={t ? `${t.patients} patient${t.patients === 1 ? '' : 's'}` : 'loading…'}
          tone="border-amber-300 bg-amber-50" testId="stat-pending" />
        <Stat label="Not invoiced yet" value={t ? rupeesLabel(t.not_invoiced_paise) : '—'} sub="charges waiting to be billed" testId="stat-not-invoiced" />
        <Stat label="Invoiced, unpaid" value={t ? rupeesLabel(t.invoiced_unpaid_paise) : '—'} sub="issued, money not yet received" testId="stat-invoiced" />
        <Stat label="Collected today" value={today.data ? rupeesLabel(today.data.collected_paise) : '—'}
          sub={today.data ? `${today.data.receipts} receipt${today.data.receipts === 1 ? '' : 's'} · all counters` : 'loading…'} tone="border-brand bg-brand-subtle" testId="stat-collected" />
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <FilterPills options={FILTERS} active={filter} onChange={(k) => { setFilter(k); setPage(1); }} />
        <FilterPills options={SOURCES} active={source} onChange={(k) => { setSource(k); setPage(1); }} />
        <div className="ml-auto flex items-center gap-2">
          <SearchInput value={search} onChange={(v) => { setSearch(v); applySearch(v); }} placeholder="Search patient or UHID" className="w-64" />
          <AppButton variant="outline" onClick={exportRows} disabled={!rows.length} data-testid="export-pending">Export</AppButton>
        </div>
      </div>

      <DataCard noPadding>
        {list.error ? <ErrorState message={list.error} onRetry={refresh} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="pending-table">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className={TH}>Patient</th><th className={TH}>Charges from</th>
                  <th className={`${TH} text-right`}>Not invoiced</th><th className={`${TH} text-right`}>Invoiced, unpaid</th>
                  <th className={`${TH} text-right`}>Balance</th><th className={TH}>Last activity</th><th className={`${TH} text-right`}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {list.loading ? <tr><td colSpan={7} className="p-0"><TableSkeleton rows={5} columns={7} /></td></tr>
                  : rows.length === 0 ? (
                    <tr><td colSpan={7}><EmptyState icon={Receipt} title="Nothing pending"
                      description="Every patient is settled. New charges appear here as visits are checked in." /></td></tr>
                  ) : rows.map((r) => (
                    <tr key={r.patient_id} className="hover:bg-brand-tint transition-colors" data-testid={`pending-row-${r.patient_id}`}>
                      <td className="px-4 py-3 whitespace-nowrap"><p className="font-medium text-gray-900">{r.patient_name}</p>
                        <p className="text-xs font-mono text-gray-500">{r.patient_uhid || ''}</p></td>
                      <td className="px-4 py-3 whitespace-nowrap"><span className="inline-flex gap-1">{r.sources.map((s) => <SourceBadge key={s} source={s} />)}</span></td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">{r.not_invoiced_paise ? rupeesLabel(r.not_invoiced_paise) : '—'}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">{r.invoiced_unpaid_paise ? rupeesLabel(r.invoiced_unpaid_paise) : '—'}</td>
                      <td className="px-4 py-3 text-right font-semibold whitespace-nowrap" data-testid={`balance-${r.patient_id}`}>{rupeesLabel(r.balance_paise)}</td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{formatDate(r.last_activity)}{r.has_part_paid ? ' · part-paid' : ''}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <AppButton variant="outline" size="sm" onClick={() => navigate(ROUTES.PATIENT_BILLING.ACCOUNT(r.patient_id))}
                          data-testid={`open-bill-${r.patient_id}`}>Open bill</AppButton>{' '}
                        <AppButton size="sm" loading={busyId === r.patient_id} onClick={() => start(r.patient_id, r.patient_name)}
                          data-testid={`collect-${r.patient_id}`}>Collect</AppButton>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationBar {...pageBarProps(page, setPage, list.data?.pagination)} />
      </DataCard>
      {dialog}
    </div>
  );
}
