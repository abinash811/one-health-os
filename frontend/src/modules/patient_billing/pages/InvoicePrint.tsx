/**
 * Printable invoice + receipt — clean A4, no app chrome. Route: /patient-billing/invoices/:id/print
 * (rendered outside <Layout>). Clinic identity comes from EMR Settings when available, otherwise the
 * invoice prints without a letterhead rather than failing.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Printer } from 'lucide-react';
import { AppButton, ErrorState, PageSkeleton, StatusBadge } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { formatDate } from '@/utils/dates';
import { MODE_LABELS, rupeesLabel } from '../money';
import type { PbInvoice } from '../types';

interface Letterhead { name: string; address: string; phone: string; registration_no: string | null; footer: string | null }

const Row = ({ label, value, strong }: { label: string; value: string; strong?: boolean }) => (
  <div className={`flex justify-between py-1 text-sm ${strong ? 'font-bold text-base border-t border-gray-300 mt-1 pt-2' : ''}`}>
    <span>{label}</span><span>{value}</span>
  </div>
);

export default function InvoicePrint() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [invoice, setInvoice] = useState<PbInvoice | null>(null);
  const [head, setHead] = useState<Letterhead | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(apiUrl.pbInvoice(id)).then((res: { data: PbInvoice }) => setInvoice(res.data))
      .catch((err: Error) => setError(err.message));
    // Best-effort: no permission / EMR off simply means no letterhead.
    api.get(apiUrl.emrSettings()).then((res: { data: { clinic_name: string | null; clinic_address: string | null;
      clinic_phone: string | null; registration_no: string | null; rx_footer: string | null;
      fallback: { clinic_name: string; clinic_address: string; clinic_phone: string } } }) => {
      const s = res.data;
      setHead({ name: s.clinic_name || s.fallback.clinic_name, address: s.clinic_address || s.fallback.clinic_address,
        phone: s.clinic_phone || s.fallback.clinic_phone, registration_no: s.registration_no, footer: s.rx_footer });
    }).catch(() => setHead(null));
  }, [id]);

  if (error) return <div className="p-8"><ErrorState message={error} /></div>;
  if (!invoice) return <PageSkeleton />;

  const cancelled = invoice.status === 'cancelled';
  return (
    <div className="min-h-screen bg-page print:bg-white py-6 print:py-0" data-testid="invoice-print-page">
      <div className="max-w-[210mm] mx-auto mb-4 flex items-center justify-between print:hidden px-2">
        <AppButton variant="outline" icon={<ArrowLeft className="w-4 h-4" />} onClick={() => navigate(-1)}>Back</AppButton>
        <AppButton icon={<Printer className="w-4 h-4" />} onClick={() => window.print()} data-testid="print-btn">
          Print / Save as PDF
        </AppButton>
      </div>

      <article className="relative max-w-[210mm] min-h-[270mm] mx-auto bg-white shadow-sm border border-gray-200 print:shadow-none print:border-0 p-10">
        {cancelled && <p className="absolute top-4 right-6 text-xs font-bold uppercase text-red-600" data-testid="invoice-cancelled">Cancelled</p>}
        {head && (
          <header className="border-b-2 border-gray-900 pb-3 mb-4">
            <h1 className="font-display text-2xl font-bold text-gray-900" data-testid="invoice-clinic-name">{head.name}</h1>
            <p className="text-xs text-gray-600">{[head.address, head.phone].filter(Boolean).join(' · ')}</p>
            {head.registration_no && <p className="text-xs text-gray-500">Reg. no. {head.registration_no}</p>}
          </header>
        )}

        <div className="flex justify-between text-sm mb-5">
          <div>
            <p className="font-semibold text-gray-900 text-base" data-testid="invoice-patient">{invoice.patient_name}</p>
            {invoice.patient_uhid && <p className="text-gray-600">{invoice.patient_uhid}</p>}
          </div>
          <div className="text-right">
            <p className="font-mono font-semibold" data-testid="invoice-number">{invoice.invoice_number}</p>
            <p className="text-gray-600">{formatDate(invoice.created_at)}</p>
            <StatusBadge status={invoice.status} />
          </div>
        </div>

        <table className="w-full text-sm mb-4" data-testid="invoice-lines">
          <thead>
            <tr className="border-b border-gray-300 text-left text-[11px] uppercase text-gray-500">
              <th className="py-1 w-8">#</th><th className="py-1">Description</th>
              <th className="py-1 text-right">Qty</th><th className="py-1 text-right">Rate</th><th className="py-1 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines.map((l, n) => (
              <tr key={l.charge_id} className="border-b border-gray-100">
                <td className="py-2 text-gray-500">{n + 1}</td><td className="py-2 font-medium text-gray-900">{l.description}</td>
                <td className="py-2 text-right">{l.quantity}</td>
                <td className="py-2 text-right">{rupeesLabel(l.unit_price_paise)}</td>
                <td className="py-2 text-right">{rupeesLabel(l.total_paise)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="w-64 ml-auto mb-6" data-testid="invoice-totals">
          <Row label="Gross" value={rupeesLabel(invoice.gross_paise)} />
          {invoice.discount_paise > 0 && <Row label="Discount" value={`− ${rupeesLabel(invoice.discount_paise)}`} />}
          <Row label="Net" value={rupeesLabel(invoice.net_paise)} />
          <Row label="Paid" value={rupeesLabel(invoice.paid_paise)} />
          <Row label="Balance" value={rupeesLabel(invoice.balance_paise)} strong />
        </div>

        {!!invoice.payments?.length && (
          <section data-testid="invoice-receipts">
            <h2 className="text-[11px] font-bold uppercase tracking-wider text-gray-500 mb-1">Receipts</h2>
            <table className="w-full text-sm">
              <tbody>
                {invoice.payments.map((p) => (
                  <tr key={p.id} className="border-b border-gray-100">
                    <td className="py-1 font-mono">{p.receipt_number}</td><td className="py-1">{formatDate(p.paid_on)}</td>
                    <td className="py-1">{MODE_LABELS[p.mode] || p.mode}{p.reference ? ` · ${p.reference}` : ''}</td>
                    <td className="py-1 text-right font-medium">{rupeesLabel(p.amount_paise)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {head?.footer && (
          <p className="absolute bottom-6 left-10 right-10 text-center text-[11px] text-gray-500 border-t pt-2" data-testid="invoice-footer">{head.footer}</p>
        )}
      </article>
    </div>
  );
}
