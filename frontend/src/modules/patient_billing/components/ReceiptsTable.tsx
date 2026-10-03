import React from 'react';
import { Printer, ReceiptText } from 'lucide-react';
import { AppButton, EmptyState, TableSkeleton } from '@/components/shared';
import { ROUTES } from '@/constants/routes';
import { useNavigate } from 'react-router-dom';
import { formatDate } from '@/utils/dates';
import { MODE_LABELS, rupeesLabel } from '../money';
import type { PbPayment } from '../types';

const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';

export interface ReceiptsTableProps {
  rows: PbPayment[];
  loading: boolean;
  emptyText?: string;
}

/** Receipts, one per payment taken — used by the Receipts tab and the Day closing tab. */
export default function ReceiptsTable({ rows, loading, emptyText = 'Receipts appear here as payments are collected.' }: ReceiptsTableProps) {
  const navigate = useNavigate();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="receipts-table">
        <thead className="bg-gray-50 border-b"><tr>
          <th className={TH}>Receipt</th><th className={TH}>Date</th><th className={TH}>Patient</th><th className={TH}>Invoice</th>
          <th className={TH}>Mode</th><th className={`${TH} text-right`}>Amount</th><th className={`${TH} text-right`}>Print</th>
        </tr></thead>
        <tbody className="divide-y">
          {loading ? <tr><td colSpan={7} className="p-0"><TableSkeleton rows={5} columns={7} /></td></tr>
            : rows.length === 0 ? <tr><td colSpan={7}><EmptyState icon={ReceiptText} title="No receipts" description={emptyText} /></td></tr>
            : rows.map((p) => (
              <tr key={p.id} className="hover:bg-brand-tint transition-colors" data-testid={`receipt-row-${p.id}`}>
                <td className="px-4 py-3 font-mono font-semibold whitespace-nowrap">{p.receipt_number}</td>
                <td className="px-4 py-3 whitespace-nowrap">{formatDate(p.paid_on)}</td>
                <td className="px-4 py-3"><p className="font-medium text-gray-900">{p.patient_name || '—'}</p>
                  <p className="text-xs font-mono text-gray-500">{p.patient_uhid || ''}</p></td>
                <td className="px-4 py-3 font-mono whitespace-nowrap">{p.invoice_number}</td>
                <td className="px-4 py-3 whitespace-nowrap">{MODE_LABELS[p.mode] || p.mode}{p.reference ? ` · ${p.reference}` : ''}</td>
                <td className="px-4 py-3 text-right font-semibold whitespace-nowrap">{rupeesLabel(p.amount_paise)}</td>
                <td className="px-4 py-3 text-right">
                  <AppButton variant="ghost" size="sm" iconOnly icon={<Printer className="w-4 h-4" />} aria-label={`Print ${p.receipt_number}`}
                    onClick={() => navigate(ROUTES.PATIENT_BILLING.INVOICE_PRINT(p.invoice_id))} data-testid={`print-receipt-${p.id}`} />
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
