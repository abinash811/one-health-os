/**
 * Add / edit a clinic (Settings → Organisation → Clinics). Only the name is required — a clinic can be
 * created in seconds and completed later. Clinics are EMR places, separate from pharmacies.
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import type { Clinic } from './types';

const fieldCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';

const BLANK = { name: '', phone: '', address: '', city: '', state: '', pincode: '', email: '', registration_no: '' };
type FormState = typeof BLANK;

interface Props {
  open: boolean;
  /** null = add a new clinic. */
  clinic: Clinic | null;
  onClose: () => void;
  onSaved: () => void;
}

const FIELDS: { key: keyof FormState; label: string; wide?: boolean; maxLength?: number }[] = [
  { key: 'name', label: 'Clinic name *', wide: true },
  { key: 'phone', label: 'Phone', maxLength: 20 },
  { key: 'email', label: 'Email' },
  { key: 'address', label: 'Address', wide: true },
  { key: 'city', label: 'City' },
  { key: 'state', label: 'State' },
  { key: 'pincode', label: 'Pincode', maxLength: 6 },
  { key: 'registration_no', label: 'Registration no.' },
];

export default function ClinicFormModal({ open, clinic, onClose, onSaved }: Props) {
  const [f, setF] = useState<FormState>(BLANK);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setF(clinic ? {
      name: clinic.name, phone: clinic.phone || '', address: clinic.address || '', city: clinic.city || '',
      state: clinic.state || '', pincode: clinic.pincode || '', email: clinic.email || '',
      registration_no: clinic.registration_no || '',
    } : BLANK);
  }, [open, clinic]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (clinic) await api.put(apiUrl.clinic(clinic.id), f);
      else await api.post(apiUrl.clinics(), f);
      toast.success(clinic ? 'Clinic saved' : 'Clinic added');
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{clinic ? 'Edit clinic' : 'Add clinic'}</DialogTitle>
          <DialogDescription>
            {clinic ? 'Change the clinic’s details.' : 'A clinic is where patients are seen. Pharmacies are added separately.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="mt-2" data-testid="clinic-form">
          <div className="grid grid-cols-2 gap-3">
            {FIELDS.map((fld) => (
              <div key={fld.key} className={fld.wide ? 'col-span-2' : ''}>
                <label htmlFor={`clinic-${fld.key}`} className={labelCls}>{fld.label}</label>
                <input id={`clinic-${fld.key}`} value={f[fld.key]} maxLength={fld.maxLength}
                  onChange={(e) => setF((s) => ({ ...s, [fld.key]: e.target.value }))}
                  className={fieldCls} data-testid={`clinic-${fld.key}`} />
              </div>
            ))}
          </div>
          <DialogFooter className="mt-6">
            <AppButton type="button" variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
            <AppButton type="submit" loading={busy} disabled={f.name.trim() === ''} data-testid="clinic-save-btn">
              {clinic ? 'Save' : 'Add clinic'}
            </AppButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
