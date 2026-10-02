import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { toPaise, toRupees } from '@/utils/currency';
import { fieldCls, labelCls } from './settingsShared';
import type { EmrDoctorProfile } from '../types';

export interface DoctorProfileModalProps {
  doctor: EmrDoctorProfile | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function DoctorProfileModal({ doctor, onClose, onSaved }: DoctorProfileModalProps) {
  const [specialty, setSpecialty] = useState('');
  const [qualification, setQualification] = useState('');
  const [registration, setRegistration] = useState('');
  const [fee, setFee] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSpecialty(doctor?.specialty || ''); setQualification(doctor?.qualification || '');
    setRegistration(doctor?.registration_no || '');
    setFee(doctor?.consultation_fee_paise ? String(toRupees(doctor.consultation_fee_paise)) : '');
  }, [doctor]);

  const feeInvalid = fee.trim() !== '' && !(Number(fee) >= 0);

  const submit = async () => {
    if (!doctor) return;
    setBusy(true);
    try {
      await api.put(apiUrl.emrDoctorProfile(doctor.user_id), {
        specialty, qualification, registration_no: registration,
        consultation_fee_paise: fee.trim() === '' ? null : toPaise(fee),
      });
      toast.success('Doctor profile saved');
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const field = (id: string, label: string, value: string, set: (v: string) => void, placeholder: string) => (
    <div>
      <label htmlFor={id} className={labelCls}>{label}</label>
      <input id={id} value={value} onChange={(e) => set(e.target.value)} placeholder={placeholder}
        className={fieldCls} data-testid={id} />
    </div>
  );

  return (
    <Dialog open={!!doctor} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{doctor?.name}</DialogTitle>
          <DialogDescription>Shown under the doctor&apos;s name on printed prescriptions.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {field('dp-specialty', 'Specialty', specialty, setSpecialty, 'e.g. Paediatrics')}
          {field('dp-qualification', 'Qualification', qualification, setQualification, 'e.g. MBBS, MD')}
          {field('dp-registration', 'Medical registration no.', registration, setRegistration, 'e.g. KMC-12345')}
          <div>
            <label htmlFor="dp-fee" className={labelCls}>Consultation fee (₹)</label>
            <input id="dp-fee" type="number" min="0" step="1" value={fee} onChange={(e) => setFee(e.target.value)}
              placeholder="e.g. 500 — leave blank for no fee" className={fieldCls} data-testid="dp-fee"
              aria-invalid={feeInvalid} />
            <p className="text-xs text-gray-500 mt-1">Added to the patient's bill when they check in.</p>
          </div>
        </div>
        <DialogFooter className="mt-6">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
          <AppButton onClick={submit} loading={busy} disabled={feeInvalid} data-testid="dp-save-btn">Save</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
