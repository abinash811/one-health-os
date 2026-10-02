import React, { useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

export interface CancelPrescriptionDialogProps {
  open: boolean;
  prescriptionId: string;
  rxNumber: string;
  onClose: () => void;
  onCancelled: () => void;
}

/** Cancelling needs a reason (backend 422s without one); a cancelled Rx frees the visit for a replacement. */
export default function CancelPrescriptionDialog({ open, prescriptionId, rxNumber, onClose, onCancelled }: CancelPrescriptionDialogProps) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(apiUrl.emrPrescriptionCancel(prescriptionId), { reason: reason.trim() });
      toast.success(`${rxNumber} cancelled`);
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
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cancel {rxNumber}</DialogTitle>
          <DialogDescription>The prescription stays on record as cancelled. You can write a new one for this visit.</DialogDescription>
        </DialogHeader>
        <label htmlFor="rx-cancel-reason" className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Reason *</label>
        <textarea id="rx-cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
          placeholder="e.g. Wrong medicine added"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm resize-none"
          data-testid="rx-cancel-reason-input" />
        <DialogFooter className="mt-4">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Keep prescription</AppButton>
          <AppButton variant="danger" onClick={submit} loading={busy} disabled={!reason.trim()}
            data-testid="rx-confirm-cancel-btn">Cancel prescription</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
