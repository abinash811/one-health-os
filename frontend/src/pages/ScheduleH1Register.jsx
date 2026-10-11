/**
 * ScheduleH1Register — Drug Register for Schedule H1 substances.
 * Route: /compliance/schedule-h1
 *
 * Accessible only by admin and manager roles.
 * Shows all dispensed Schedule H1 drugs: drug, qty, batch, prescriber, patient.
 */
import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Printer, Download, AlertTriangle } from 'lucide-react';
import {
  PageHeader, DataCard, DateRangePicker,
  SearchInput, TableSkeleton, PaginationBar, AppButton,
} from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { useDebounce } from '@/hooks/useDebounce';
import { formatDateShort, toISODate } from '@/utils/dates';
import usePagination from '@/hooks/usePagination';

export default function ScheduleH1Register() {
  const [entries, setEntries]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery]   = useState('');
  const debouncedSearch                 = useDebounce(searchQuery, 300);
  const [dateRange, setDateRange]       = useState({ start: null, end: null });

  // Client-side pagination (data is usually small and already filtered by date server-side)
  const pg = usePagination({ pageSize: 20 });

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateRange.start) params.from_date = toISODate(dateRange.start);
      if (dateRange.end)   params.to_date   = toISODate(dateRange.end);

      const res = await api.get(apiUrl.scheduleH1(params));
      setEntries(res.data.entries || []);
    } catch (err) {
      if (err.response?.status === 403) {
        setAccessDenied(true);
      } else {
        toast.error(err.response?.data?.detail || err.message || 'Failed to load Schedule H1 register');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateRange]);

  // Client-side search filter
  const filtered = entries.filter((e) => {
    if (!debouncedSearch) return true;
    const q = debouncedSearch.toLowerCase();
    return (
      e.product_name?.toLowerCase().includes(q) ||
      e.prescriber_name?.toLowerCase().includes(q) ||
      e.patient_name?.toLowerCase().includes(q) ||
      e.batch_number?.toLowerCase().includes(q)
    );
  });

  useEffect(() => {
    pg.resetPage();
    pg.setTotal(filtered.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, entries.length]);

  const pageRows = pg.slice(filtered);

  const handlePrint = () => window.print();

  const handleExportCSV = () => {
    const headers = ['Date', 'Drug Name', 'Qty', 'Batch', 'Prescriber', 'Reg No.', 'Patient', 'Patient Address', 'Age'];
    const rows = filtered.map((e) => [
      e.supply_date, e.product_name, e.quantity, e.batch_number,
      e.prescriber_name, e.prescriber_registration_number,
      e.patient_name, e.patient_address, e.patient_age,
    ]);
    const csv = [headers, ...rows].map((r) => r.map((v) => `"${v ?? ''}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), { href: url, download: 'schedule-h1-register.csv' });
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Exported to CSV');
  };

  if (accessDenied) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md">
          <AlertTriangle className="w-16 h-16 text-amber-500 mx-auto mb-4" />
          <h1 className="text-xl font-bold text-gray-800 mb-2">Access Restricted</h1>
          <p className="text-gray-600">
            The Schedule H1 Drug Register is only accessible to <strong>Admin</strong> and <strong>Manager</strong> roles.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-6 min-h-screen bg-page print:p-0 print:bg-white" data-testid="schedule-h1-page">
      <PageHeader
        title="Schedule H1 Drug Register"
        actions={
          <div className="flex gap-2 print:hidden">
            <AppButton variant="outline" onClick={handleExportCSV} disabled={filtered.length === 0}>
              <Download className="w-4 h-4 mr-2" />
              Export CSV
            </AppButton>
            <AppButton variant="outline" onClick={handlePrint} disabled={filtered.length === 0}>
              <Printer className="w-4 h-4 mr-2" />
              Print
            </AppButton>
          </div>
        }
      />

      {/* Regulatory notice */}
      <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-amber-800">
          This register is automatically populated when Schedule H1 drugs are dispensed through billing.
          Records are maintained as per CDSCO / State licensing authority requirements.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-4 print:hidden">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Drug, patient, prescriber..."
          className="w-64"
        />
        <DateRangePicker dateRange={dateRange} onDateRangeChange={setDateRange} />
        {(dateRange.start || dateRange.end) && (
          <AppButton
            variant="ghost"
            size="sm"
            onClick={() => setDateRange({ start: null, end: null })}
          >
            Clear
          </AppButton>
        )}
      </div>

      {/* Table */}
      <DataCard>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="h1-register-table">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Drug Name</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Qty</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Batch</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Prescribing Doctor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Reg. No.</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Patient</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Address</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Age</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan="9" className="p-0">
                    <TableSkeleton rows={6} columns={8} />
                  </td>
                </tr>
              ) : pageRows.length === 0 ? (
                <tr>
                  <td colSpan="9" className="py-16 text-center text-gray-400">
                    {debouncedSearch || dateRange.start
                      ? 'No entries match your search.'
                      : 'No Schedule H1 entries yet. They are auto-created when H1 drugs are dispensed.'}
                  </td>
                </tr>
              ) : (
                pageRows.map((entry) => (
                  <tr key={entry.id} className="hover:bg-brand-tint transition-colors" data-testid={`h1-row-${entry.id}`}>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="text-sm text-gray-700">{formatDateShort(entry.supply_date)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-800">{entry.product_name}</div>
                    </td>
                    <td className="px-4 py-3 text-center font-mono font-semibold text-gray-700">
                      {entry.quantity}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">{entry.batch_number || '—'}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-800">{entry.prescriber_name || '—'}</div>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600 font-mono">
                      {entry.prescriber_registration_number || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-800">{entry.patient_name || '—'}</div>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600 max-w-[150px] truncate" title={entry.patient_address}>
                      {entry.patient_address || '—'}
                    </td>
                    <td className="px-4 py-3 text-center text-gray-600">{entry.patient_age || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        <PaginationBar {...pg} />
      </DataCard>

      {/* Print styles */}
      <style>{`
        @media print {
          .print\\:hidden { display: none !important; }
          .print\\:p-0 { padding: 0 !important; }
          .print\\:bg-white { background: white !important; }
        }
      `}</style>
    </div>
  );
}
