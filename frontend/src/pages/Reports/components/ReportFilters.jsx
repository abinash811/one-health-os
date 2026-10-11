import React from 'react';
import { RefreshCw, Download, FileSpreadsheet } from 'lucide-react';
import { AppButton, DateRangePicker } from '@/components/shared';

export default function ReportFilters({
  activeReport, dateRange, expiryDays, hasData,
  onDateChange, onExpiryChange, onRefresh, onExportCSV, onExportExcel,
}) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {['sales', 'margin', 'sales-returns', 'purchase-returns', 'purchase-payments', 'supplier-analytics', 'purchase-variance', 'batch-purchases', 'price-variation'].includes(activeReport) && (
        <DateRangePicker dateRange={dateRange} onDateRangeChange={onDateChange} />
      )}

      {activeReport === 'expiry' && (
        <div className="flex items-center gap-2">
          <label htmlFor="fld-reportfiltersjsx-17" className="text-sm font-medium text-gray-600">Expiring in:</label>
          <select id="fld-reportfiltersjsx-17"
            value={expiryDays}
            onChange={(e) => onExpiryChange(parseInt(e.target.value))}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            data-testid="expiry-days"
          >
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
          </select>
        </div>
      )}

      <AppButton variant="outline" icon={<RefreshCw className="w-4 h-4" strokeWidth={1.5} />} onClick={onRefresh}>
        Refresh
      </AppButton>
      <AppButton variant="outline" icon={<Download className="w-4 h-4" strokeWidth={1.5} />} onClick={onExportCSV} disabled={!hasData} data-testid="export-csv-btn">
        Export CSV
      </AppButton>
      <AppButton variant="outline" icon={<FileSpreadsheet className="w-4 h-4" strokeWidth={1.5} />} onClick={onExportExcel} disabled={!hasData} data-testid="export-excel-btn">
        Export Excel
      </AppButton>
    </div>
  );
}
