import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { toPaise, toRupees } from '@/utils/currency';
import { fieldCls, labelCls } from './settingsShared';
import type { EmrClinicDoctor } from '../types';

export interface DoctorFeeModalProps {
  doctor: EmrClinicDoctor | null;
  onClose: () => void;
  onSaved: () => void;
}

/** This clinic's consultation fee for one doctor. The doctor's profile (name, registration…) is the hospital's
 *  and is edited under Settings → Organisation → Doctors. */
export default function DoctorFeeModal({ doctor, onClose, onSaved }: DoctorFeeModalProps) {
  const [fee, setFee] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setFee(doctor?.consultation_fee_paise ? String(toRupees(doctor.consultation_fee_paise)) : '');
  }, [doctor]);

  const feeInvalid = fee.trim() !== '' && !(Number(fee) >= 0);

  const submit = async () => {
    if (!doctor) return;
    setBusy(true);
    try {
      await api.put(apiUrl.emrClinicDoctor(doctor.id), {
        consultation_fee_paise: fee.trim() === '' ? null : toPaise(fee),
      });
      toast.success('Consultation fee saved');
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={!!doctor} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{doctor?.name}</DialogTitle>
          <DialogDescription>Consultation fee at this clinic. Added to the patient&apos;s bill when they check in.</DialogDescription>
        </DialogHeader>
        <div>
          <label htmlFor="dp-fee" className={labelCls}>Consultation fee (₹)</label>
          <input id="dp-fee" type="number" min="0" step="1" value={fee} onChange={(e) => setFee(e.target.value)}
            placeholder="e.g. 500 — leave blank for no fee" className={fieldCls} data-testid="dp-fee"
            aria-invalid={feeInvalid} />
          <p className="text-xs text-gray-500 mt-1">To change the doctor&apos;s name, registration number or the clinics they work at, use Settings → Organisation → Doctors.</p>
        </div>
        <DialogFooter className="mt-6">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
          <AppButton onClick={submit} loading={busy} disabled={feeInvalid} data-testid="dp-save-btn">Save</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
