/**
 * AccountBill — one patient's complete bill: every charge (from any module), the invoices made from
 * them, the receipts taken, and what is still owed. Used by the billing desk's account page and by
 * the Billing tab on the EMR patient profile.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Printer, Receipt } from 'lucide-react';
import { DataCard, AppButton, EmptyState, ErrorState, TableSkeleton } from '@/components/shared';
import { apiUrl } from '@/constants/api';
import { CHARGE_STATUS } from '@/constants/domainConstants';
import { ROUTES } from '@/constants/routes';
import { formatDate } from '@/utils/dates';
import { useClinicAccess } from '@/utils/clinicAccess';
import { MODE_LABELS, rupeesLabel } from '../money';
import { useQuery } from '../useQuery';
import { ChargeBadge, InvoiceBadge, SourceBadge } from './badges';
import { useCollect } from './useCollect';
import type { AccountDetail } from '../types';

const TH = 'px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';
const label = 'text-xs font-bold uppercase tracking-wide text-gray-500';

export interface AccountBillProps {
  patientId: string;
  /** Show the patient's name + UHID on top (the account page does; the profile tab already has them). */
  showPatient?: boolean;
  patientName?: string;
}

export default function AccountBill({ patientId, showPatient = true, patientName }: AccountBillProps) {
  const navigate = useNavigate();
  const [tick, setTick] = useState(0);
  const refresh = () => setTick((t) => t + 1);
  const res = useQuery<AccountDetail>(apiUrl.pbAccount(patientId), tick);
  const { start, dialog, busyId } = useCollect(refresh);
  const { canCollect } = useClinicAccess();
  const a = res.data;

  if (res.loading) return <DataCard noPadding><TableSkeleton rows={5} columns={5} /></DataCard>;
  if (res.status === 404) {   // no charges yet is not an error
    return <DataCard><EmptyState icon={Receipt} title="No charges yet"
      description="Charges appear here when the patient checks in or a service is added to their bill." /></DataCard>;
  }
  if (res.error || !a) return <DataCard><ErrorState message={res.error} onRetry={refresh} /></DataCard>;

  const t = a.totals;
  const name = a.patient.name || patientName || 'Patient';
  return (
    <div className="space-y-4" data-testid="account-bill">
      <div className="flex items-center justify-between">
        {showPatient ? (
          <div><p className="text-lg font-semibold text-gray-900" data-testid="account-patient">{name}</p>
            <p className="text-xs font-mono text-gray-500">{a.patient.uhid || ''}</p></div>
        ) : <span />}
        {canCollect && t.balance_paise > 0 && (
          <AppButton loading={busyId === patientId} onClick={() => start(patientId, name)} data-testid="account-collect">
            Collect {rupeesLabel(t.balance_paise)}
          </AppButton>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="account-totals">
        <DataCard noPadding={false}><p className={label}>Total charges</p>
          <p className="text-2xl font-bold" data-testid="total-charges">{rupeesLabel(t.total_charges_paise)}</p></DataCard>
        <DataCard noPadding={false}><p className={label}>Paid</p>
          <p className="text-2xl font-bold text-green-700" data-testid="total-paid">{rupeesLabel(t.paid_paise)}</p></DataCard>
        <DataCard noPadding={false}><p className={label}>Not invoiced</p>
          <p className="text-2xl font-bold" data-testid="total-not-invoiced">{rupeesLabel(t.not_invoiced_paise)}</p></DataCard>
        <DataCard noPadding={false} className={t.balance_paise > 0 ? 'border-amber-300 bg-amber-50' : ''}>
          <p className={label}>Balance due</p>
          <p className={`text-2xl font-bold ${t.balance_paise > 0 ? 'text-amber-700' : ''}`} data-testid="total-balance">{rupeesLabel(t.balance_paise)}</p></DataCard>
      </div>

      <DataCard noPadding>
        <div className="px-4 py-3 border-b"><span className={label}>Charges</span></div>
        <table className="w-full text-sm" data-testid="charges-table">
          <thead className="bg-gray-50 border-b"><tr><th className={TH}>Date</th><th className={TH}>Charge</th><th className={TH}>From</th>
            <th className={`${TH} text-right`}>Qty</th><th className={`${TH} text-right`}>Amount</th><th className={TH}>Status</th></tr></thead>
          <tbody className="divide-y">
            {a.charges.map((c) => (
              <tr key={c.id} className={c.status === CHARGE_STATUS.VOID ? 'text-gray-400 line-through' : ''} data-testid={`charge-row-${c.id}`}>
                <td className="px-4 py-2 whitespace-nowrap">{formatDate(c.created_at)}</td>
                <td className="px-4 py-2 font-medium">{c.description}</td>
                <td className="px-4 py-2"><SourceBadge source={c.source_module} /></td>
                <td className="px-4 py-2 text-right">{c.quantity}</td>
                <td className="px-4 py-2 text-right font-semibold whitespace-nowrap">{rupeesLabel(c.total_paise)}</td>
                <td className="px-4 py-2"><ChargeBadge status={c.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataCard>

      {a.invoices.length > 0 && (
        <DataCard noPadding>
          <div className="px-4 py-3 border-b"><span className={label}>Invoices</span></div>
          <table className="w-full text-sm" data-testid="account-invoices">
            <thead className="bg-gray-50 border-b"><tr><th className={TH}>Invoice</th><th className={TH}>Date</th>
              <th className={`${TH} text-right`}>Net</th><th className={`${TH} text-right`}>Paid</th><th className={`${TH} text-right`}>Balance</th>
              <th className={TH}>Status</th><th className={`${TH} text-right`}>Print</th></tr></thead>
            <tbody className="divide-y">
              {a.invoices.map((i) => (
                <tr key={i.id} data-testid={`account-invoice-${i.id}`}>
                  <td className="px-4 py-2 font-mono font-semibold">{i.invoice_number}</td><td className="px-4 py-2">{formatDate(i.created_at)}</td>
                  <td className="px-4 py-2 text-right">{rupeesLabel(i.net_paise)}</td><td className="px-4 py-2 text-right">{rupeesLabel(i.paid_paise)}</td>
                  <td className="px-4 py-2 text-right font-semibold">{rupeesLabel(i.balance_paise)}</td>
                  <td className="px-4 py-2"><InvoiceBadge status={i.status} /></td>
                  <td className="px-4 py-2 text-right"><AppButton variant="ghost" size="sm" iconOnly icon={<Printer className="w-4 h-4" />}
                    aria-label={`Print ${i.invoice_number}`} onClick={() => navigate(ROUTES.PATIENT_BILLING.INVOICE_PRINT(i.id))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataCard>
      )}

      {a.payments.length > 0 && (
        <DataCard noPadding>
          <div className="px-4 py-3 border-b"><span className={label}>Receipts</span></div>
          <table className="w-full text-sm" data-testid="account-payments">
            <tbody className="divide-y">
              {a.payments.map((p) => (
                <tr key={p.id}><td className="px-4 py-2 font-mono font-semibold">{p.receipt_number}</td>
                  <td className="px-4 py-2">{formatDate(p.paid_on)}</td><td className="px-4 py-2 font-mono">{p.invoice_number}</td>
                  <td className="px-4 py-2">{MODE_LABELS[p.mode] || p.mode}{p.reference ? ` · ${p.reference}` : ''}</td>
                  <td className="px-4 py-2 text-right font-semibold">{rupeesLabel(p.amount_paise)}</td></tr>
              ))}
            </tbody>
          </table>
        </DataCard>
      )}
      {dialog}
    </div>
  );
}
