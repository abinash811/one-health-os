/**
 * Collect payment — invoices the chosen unbilled charges and takes the money in one step, or pays
 * the rest of an existing part-paid invoice. Used by the queue today; the billing desk reuses it (B4).
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton, FilterPills } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { ROUTES } from '@/constants/routes';
import { BILLING_COUNTER, PAYMENT_MODE } from '@/constants/domainConstants';
import { toPaise } from '@/utils/currency';
import { MODE_LABELS, rupeesLabel } from '../money';
import type { PbInvoice, PbPayment } from '../types';

const MODE_OPTIONS = Object.values(PAYMENT_MODE).map((m) => ({ key: m, label: MODE_LABELS[m] }));
const fieldCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm aria-invalid:border-red-500';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';

export interface CollectCharge { id: string; description: string; total_paise: number }

export interface CollectPaymentDialogProps {
  open: boolean;
  patientId: string;
  patientName: string;
  /** Unbilled charges to invoice now. Ignored when `existingInvoice` is given. */
  charges: CollectCharge[];
  /** An invoice that still has a balance — pay the rest of it instead of making a new one. */
  existingInvoice?: { id: string; invoice_number: string; balance_paise: number } | null;
  counter?: string;
  onClose: () => void;
  onCollected: (result: { invoice: PbInvoice; payment: PbPayment | null }) => void;
}

export default function CollectPaymentDialog({
  open, patientId, patientName, charges, existingInvoice, counter = BILLING_COUNTER.FRONT_DESK, onClose, onCollected,
}: CollectPaymentDialogProps) {
  const navigate = useNavigate();
  const [discount, setDiscount] = useState('');
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState<string>(PAYMENT_MODE.CASH);
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setDiscount(''); setAmount(''); setMode(PAYMENT_MODE.CASH); setReference(''); }
  }, [open]);

  const gross = existingInvoice ? existingInvoice.balance_paise : charges.reduce((s, c) => s + c.total_paise, 0);
  const discountPaise = existingInvoice ? 0 : toPaise(discount);
  const net = gross - discountPaise;
  const typed = amount.trim() !== '';
  const amountPaise = typed ? toPaise(amount) : net;
  const discountError = discountPaise < 0 || discountPaise > gross ? `Discount must be between ₹0 and ${rupeesLabel(gross)}` : '';
  const amountError = !typed || net === 0 ? '' : amountPaise < 1 || amountPaise > net ? `Enter an amount up to ${rupeesLabel(net)}` : '';
  const remaining = net - (net === 0 ? 0 : amountPaise);

  const submit = async () => {
    setBusy(true);
    try {
      const res = existingInvoice
        ? await api.post(apiUrl.pbInvoicePayments(existingInvoice.id), {
          amount_paise: amountPaise, mode, reference: reference.trim() || null })
        : await api.post(apiUrl.pbCollect(patientId), {
          charge_item_ids: charges.map((c) => c.id), discount_paise: discountPaise,
          amount_paise: typed ? amountPaise : undefined, mode, reference: reference.trim() || null, counter });
      const { invoice, payment } = res.data as { invoice: PbInvoice; payment: PbPayment | null };
      toast.success(
        payment ? `Collected ${rupeesLabel(payment.amount_paise)} · ${payment.receipt_number}` : `Invoice ${invoice.invoice_number} issued`,
        { action: { label: 'Print', onClick: () => navigate(ROUTES.PATIENT_BILLING.INVOICE_PRINT(invoice.id)) } });
      onCollected({ invoice, payment });
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Collect payment</DialogTitle>
          <DialogDescription>
            {patientName}{existingInvoice ? ` · balance on ${existingInvoice.invoice_number}` : ''}
          </DialogDescription>
        </DialogHeader>

        {!existingInvoice && (
          <ul className="text-sm divide-y border rounded-lg px-3 mb-3" data-testid="collect-lines">
            {charges.map((c) => (
              <li key={c.id} className="flex justify-between py-2"><span>{c.description}</span><span>{rupeesLabel(c.total_paise)}</span></li>
            ))}
          </ul>
        )}
        <div className="flex justify-between text-sm font-semibold border-t pt-2 mb-3" data-testid="collect-total">
          <span>To pay</span><span>{rupeesLabel(Math.max(net, 0))}</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="collect-amount" className={labelCls}>Amount received (₹)</label>
            <input id="collect-amount" type="number" min="0" value={amount} disabled={net === 0}
              onChange={(e) => setAmount(e.target.value)} placeholder={String(net / 100)} aria-invalid={!!amountError}
              className={fieldCls} data-testid="collect-amount" />
          </div>
          {!existingInvoice && (
            <div>
              <label htmlFor="collect-discount" className={labelCls}>Discount (₹)</label>
              <input id="collect-discount" type="number" min="0" value={discount} onChange={(e) => setDiscount(e.target.value)}
                aria-invalid={!!discountError} className={fieldCls} data-testid="collect-discount" />
            </div>
          )}
        </div>
        {(amountError || discountError) && (
          <p role="alert" className="text-xs text-red-500 mt-1" data-testid="collect-error">{amountError || discountError}</p>
        )}
        {remaining > 0 && !amountError && typed && (
          <p className="text-xs text-gray-500 mt-1" data-testid="collect-remaining">{rupeesLabel(remaining)} will stay as balance.</p>
        )}

        <span className={`${labelCls} mt-3`}>Payment mode</span>
        <FilterPills options={MODE_OPTIONS} active={mode} onChange={setMode} />
        {mode !== PAYMENT_MODE.CASH && (
          <div className="mt-3">
            <label htmlFor="collect-ref" className={labelCls}>{mode === PAYMENT_MODE.UPI ? 'UPI reference' : 'Card last 4 digits'}</label>
            <input id="collect-ref" value={reference} onChange={(e) => setReference(e.target.value)}
              placeholder="optional" className={fieldCls} data-testid="collect-ref" />
          </div>
        )}

        <DialogFooter className="mt-5">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
          <AppButton onClick={submit} loading={busy} disabled={!!amountError || !!discountError || gross <= 0}
            data-testid="collect-submit-btn">
            {net === 0 ? 'Issue invoice' : `Collect ${rupeesLabel(amountPaise)}`}
          </AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
