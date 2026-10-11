import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Printer, Eye } from 'lucide-react';
import {
  PageHeader, PageTabs, DataCard, SearchInput, StatusBadge,
  DateRangePicker, TableSkeleton, SalesReturnsEmptyState, PaginationBar,
  FilterPills, AppButton,
} from '../components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { useDebounce } from '@/hooks/useDebounce';
import { formatDateShort, formatTime, toISODate } from '@/utils/dates';
import usePagination from '@/hooks/usePagination';

const BILLING_TABS = [
  { key: 'bills',   label: 'Bills'         },
  { key: 'returns', label: 'Sales Returns' },
];

export default function SalesReturnsList() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(true);

  // Search & filters — dateRange can arrive pre-set via URL (?from_date=&
  // to_date=) so the Dashboard's "Returns (Month)" card drills straight
  // into the same window it counted.
  const [searchQuery, setSearchQuery]   = useState('');
  const debouncedSearch                 = useDebounce(searchQuery, 300);
  const [activeFilter, setActiveFilter] = useState('all');
  const [dateRange, setDateRange]       = useState(() => {
    const from = searchParams.get('from_date');
    const to   = searchParams.get('to_date');
    return from && to ? { start: new Date(from), end: new Date(to) } : { start: null, end: null };
  });

  // Pagination
  const pg = usePagination({ pageSize: 20 });

  // ── Fetch ────────────────────────────────────────────────────────────────────
  const fetchData = async (pageOverride) => {
    setLoading(true);
    try {
      const params = {
        page:      pageOverride ?? pg.page,
        page_size: pg.pageSize,
      };
      if (debouncedSearch)          params.search       = debouncedSearch;
      if (activeFilter !== 'all')   params.payment_type = activeFilter;
      if (dateRange.start)          params.from_date    = toISODate(dateRange.start);
      if (dateRange.end)            params.to_date      = toISODate(dateRange.end);

      const res = await api.get(apiUrl.salesReturns(params));
      setReturns(res.data.data || []);
      pg.setFromResponse(res.data.pagination);
    } catch {
      toast.error('Failed to load sales returns');
    } finally {
      setLoading(false);
    }
  };

  // Re-fetch when filters change — reset to page 1
  useEffect(() => {
    pg.resetPage();
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, activeFilter, dateRange]);

  // Re-fetch when page changes
  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pg.page]);

  const isFiltered = !!(searchQuery || dateRange.start || dateRange.end || activeFilter !== 'all');

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="sales-returns-page">
      <PageHeader
        title="Billing"
        actions={
          <AppButton onClick={() => navigate('/billing/returns/new')} data-testid="new-return-btn">
            <Plus className="w-4 h-4 mr-2" />
            New Return
          </AppButton>
        }
      />
      <PageTabs
        tabs={BILLING_TABS}
        activeTab="returns"
        onChange={() => navigate('/billing')}
      />

      {/* Filters Row */}
      <div className="flex justify-between items-center gap-4 mb-4">
        <div className="flex items-center gap-4">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Return no., bill no., patient..."
            className="w-64"
          />

          <DateRangePicker dateRange={dateRange} onDateRangeChange={setDateRange} />

          <FilterPills
            options={[
              { key: 'all',               label: 'All'    },
              { key: 'cash',              label: 'Cash'   },
              { key: 'upi',               label: 'UPI'    },
              { key: 'credit_to_account', label: 'Credit' },
            ]}
            active={activeFilter}
            onChange={setActiveFilter}
          />
        </div>
      </div>

      {/* Table */}
      <DataCard>
        <div className="overflow-x-auto">
          <table className="w-full" data-testid="sales-returns-table">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Return No.</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Original Bill</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Patient</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Entry Date</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Return Date</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Entry By</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Amount</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Payment</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan="9" className="p-0">
                    <TableSkeleton rows={6} columns={8} />
                  </td>
                </tr>
              ) : returns.length === 0 ? (
                <tr>
                  <td colSpan="9" className="p-0">
                    <SalesReturnsEmptyState
                      filtered={isFiltered}
                      action={
                        <AppButton onClick={() => navigate('/billing/returns/new')} data-testid="empty-new-return-btn">
                          <Plus className="w-4 h-4 mr-2" />
                          New Sales Return
                        </AppButton>
                      }
                    />
                  </td>
                </tr>
              ) : (
                returns.map((item) => (
                  <tr
                    key={item.id}
                    className="hover:bg-brand-tint cursor-pointer"
                    onClick={() => navigate(`/billing/returns/${item.id}`)}
                    data-testid={`return-row-${item.return_no}`}
                  >
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm font-semibold text-brand">
                        #{item.return_no}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {item.original_bill_no ? (
                        <span className="font-mono text-sm text-gray-700">#{item.original_bill_no}</span>
                      ) : (
                        <span className="text-xs text-gray-400 italic">Manual</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-800">{item.patient?.name || 'Walk-in'}</div>
                      {item.patient?.phone && (
                        <div className="text-xs text-gray-500">{item.patient.phone}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {/* Entry Date column showed nothing — the backend
                          response has no "entry_date" field at all (only
                          "created_at" and "return_date"); the header
                          existed but the data behind it never did. Found
                          Sep 19, 2026 (Abinash). */}
                      <div className="text-sm text-gray-700">{formatDateShort(item.created_at)}</div>
                      <div className="text-xs text-gray-500">{formatTime(item.created_at)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm text-gray-700">{formatDateShort(item.return_date)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-700">{item.created_by?.name || '-'}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="font-semibold tabular-nums text-red-600">
                        -₹{(item.net_amount || 0).toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <StatusBadge status={item.refund_method || 'cash'} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <AppButton
                          variant="ghost"
                          iconOnly
                          icon={<Eye className="w-4 h-4 text-blue-600" />}
                          aria-label="View"
                          className="p-1.5 h-auto hover:bg-blue-50"
                          onClick={(e) => { e.stopPropagation(); navigate(`/billing/returns/${item.id}`); }}
                        />
                        <AppButton
                          variant="ghost"
                          iconOnly
                          icon={<Printer className="w-4 h-4 text-gray-600" />}
                          aria-label="Print"
                          className="p-1.5 h-auto hover:bg-gray-100"
                          onClick={(e) => { e.stopPropagation(); toast.info('Print functionality coming soon'); }}
                        />
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        <PaginationBar {...pg} />
      </DataCard>
    </div>
  );
}
