import React, { useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import type { PbInvoice } from '../types';

export interface CancelInvoiceDialogProps {
  invoice: PbInvoice | null;
  onClose: () => void;
  onCancelled: () => void;
}

/** Cancelling needs a reason; its charges go back to "unbilled" so they can be invoiced again. */
export default function CancelInvoiceDialog({ invoice, onClose, onCancelled }: CancelInvoiceDialogProps) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!invoice) return;
    setBusy(true);
    try {
      await api.post(apiUrl.pbInvoiceCancel(invoice.id), { reason: reason.trim() });
      toast.success(`${invoice.invoice_number} cancelled`);
      setReason('');
      onCancelled();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={!!invoice} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cancel {invoice?.invoice_number}</DialogTitle>
          <DialogDescription>Its charges go back to unbilled so they can be invoiced again. The number is not reused.</DialogDescription>
        </DialogHeader>
        <label htmlFor="cancel-invoice-reason" className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Reason *</label>
        <textarea id="cancel-invoice-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
          placeholder="e.g. Wrong patient" data-testid="cancel-invoice-reason"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm resize-none" />
        <DialogFooter className="mt-4">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Keep invoice</AppButton>
          <AppButton variant="danger" onClick={submit} loading={busy} disabled={!reason.trim()}
            data-testid="cancel-invoice-confirm">Cancel invoice</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
