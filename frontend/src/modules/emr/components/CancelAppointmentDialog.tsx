import React, { useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { APPOINTMENT_STATUS } from '@/constants/domainConstants';
import type { EmrAppointment } from '../types';

export interface CancelAppointmentDialogProps {
  appointment: EmrAppointment | null;
  onClose: () => void;
  onCancelled: () => void;
}

/** Cancelling needs a reason (backend returns 422 without one) — asked for here, not guessed. */
export default function CancelAppointmentDialog({ appointment, onClose, onCancelled }: CancelAppointmentDialogProps) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!appointment) return;
    setBusy(true);
    try {
      await api.post(apiUrl.emrAppointmentStatus(appointment.id), {
        status: APPOINTMENT_STATUS.CANCELLED, cancel_reason: reason.trim(),
      });
      toast.success('Appointment cancelled');
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
    <Dialog open={!!appointment} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cancel appointment{appointment?.patient_name ? ` — ${appointment.patient_name}` : ''}</DialogTitle>
        </DialogHeader>
        <label htmlFor="cancel-reason" className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">
          Reason *
        </label>
        <textarea id="cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
          placeholder="e.g. Patient called to cancel"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm resize-none"
          data-testid="cancel-reason-input" />
        <DialogFooter className="mt-4">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Keep appointment</AppButton>
          <AppButton variant="danger" onClick={submit} loading={busy} disabled={!reason.trim()}
            data-testid="confirm-cancel-btn">Cancel appointment</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
