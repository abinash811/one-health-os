/**
 * Add / edit a doctor (Settings → Organisation → Doctors). A doctor is a profile, not a login:
 * profile details, which clinics they practise at (a consultation fee for each), and — optionally —
 * the login that belongs to them. No password anywhere on this form.
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import {
  Select as SelectRoot, SelectContent as SelectContentRaw, SelectItem as SelectItemRaw,
  SelectTrigger as SelectTriggerRaw, SelectValue as SelectValueRaw,
} from '@/components/ui/select';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { toPaise, toRupees } from '@/utils/currency';
import type { ClinicOption, Doctor, LinkableUser } from './types';

// select.jsx is untyped plain JS — same cast DoctorSelect.tsx uses.
type AnyProps = React.FC<Record<string, unknown> & { children?: React.ReactNode }>;
const Select = SelectRoot as unknown as AnyProps;
const SelectContent = SelectContentRaw as unknown as AnyProps;
const SelectItem = SelectItemRaw as unknown as AnyProps;
const SelectTrigger = SelectTriggerRaw as unknown as AnyProps;
const SelectValue = SelectValueRaw as unknown as AnyProps;

const fieldCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';
const NO_LOGIN = 'none';

interface Props {
  open: boolean;
  /** null = add a new doctor. */
  doctor: Doctor | null;
  clinics: ClinicOption[];
  onClose: () => void;
  onSaved: () => void;
}

interface ClinicRow { on: boolean; fee: string }

export default function DoctorFormModal({ open, doctor, clinics, onClose, onSaved }: Props) {
  const [f, setF] = useState({ name: '', specialty: '', qualification: '', registration_no: '', phone: '', email: '',
    hospital: '', notes: '', is_external: false, is_active: true });
  const [rows, setRows] = useState<Record<string, ClinicRow>>({});
  const [login, setLogin] = useState(NO_LOGIN);
  const [linkable, setLinkable] = useState<LinkableUser[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const d = doctor;
    setF({ name: d?.name || '', specialty: d?.specialty || '', qualification: d?.qualification || '',
      registration_no: d?.registration_no || '', phone: d?.phone || '', email: d?.email || '',
      hospital: d?.hospital || '', notes: d?.notes || '', is_external: d?.is_external || false, is_active: d?.is_active ?? true });
    const mapped = new Map((d?.clinics || []).map((c) => [c.clinic_id, c]));
    setRows(Object.fromEntries(clinics.map((c) => {
      const m = mapped.get(c.clinic_id);
      const on = d ? !!m : !!c.is_current;
      return [c.clinic_id, { on, fee: m?.consultation_fee_paise ? String(toRupees(m.consultation_fee_paise)) : '' }];
    })));
    setLogin(d?.user_id || NO_LOGIN);
    api.get(apiUrl.practitionerLinkableUsers()).then((r: { data: LinkableUser[] }) => setLinkable(r.data || []))
      .catch(() => setLinkable([]));
  }, [open, doctor, clinics]);

  const set = (k: keyof typeof f, v: string | boolean) => setF((s) => ({ ...s, [k]: v }));
  const feeBad = Object.values(rows).some((r) => r.on && r.fee.trim() !== '' && !(Number(r.fee) >= 0));
  const anyClinic = Object.values(rows).some((r) => r.on);
  const canSave = f.name.trim() !== '' && !feeBad && (f.is_external || anyClinic);

  const loginOptions = [
    ...(doctor?.user_id ? [{ id: doctor.user_id, name: doctor.user_name || 'Linked login', email: doctor.user_email || '' }] : []),
    ...linkable.filter((u) => u.id !== doctor?.user_id),
  ];

  const submit = async () => {
    setBusy(true);
    const body = {
      ...f, name: f.name.trim(), hospital: f.is_external ? f.hospital : '',
      user_id: login === NO_LOGIN ? null : login,
      clinics: clinics.filter((c) => rows[c.clinic_id]?.on).map((c) => ({
        clinic_id: c.clinic_id,
        consultation_fee_paise: rows[c.clinic_id].fee.trim() === '' ? null : toPaise(rows[c.clinic_id].fee),
      })),
    };
    try {
      if (doctor) await api.put(apiUrl.practitioner(doctor.id), body);
      else await api.post(apiUrl.practitioners(), body);
      toast.success(doctor ? 'Doctor saved' : `${body.name} added`);
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const text = (id: string, label: string, key: keyof typeof f, placeholder = '') => (
    <div>
      <label htmlFor={id} className={labelCls}>{label}</label>
      <input id={id} value={f[key] as string} onChange={(e) => set(key, e.target.value)} placeholder={placeholder}
        className={fieldCls} data-testid={id} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="doctor-form">
        <DialogHeader>
          <DialogTitle>{doctor ? 'Edit doctor' : 'Add doctor'}</DialogTitle>
          <DialogDescription>A doctor is a profile, separate from logins. Details print on their prescriptions.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {text('doc-name', 'Name *', 'name', 'e.g. Dr Anita Rao')}
            {text('doc-specialty', 'Specialty', 'specialty', 'e.g. Paediatrics')}
            {text('doc-qualification', 'Qualification', 'qualification', 'e.g. MBBS, MD')}
            {text('doc-registration', 'Medical registration no.', 'registration_no', 'e.g. KMC-12345')}
            {text('doc-phone', 'Phone', 'phone')}
            {text('doc-email', 'Email', 'email')}
          </div>

          <label className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer" htmlFor="doc-external">
            <input id="doc-external" type="checkbox" checked={f.is_external} onChange={(e) => set('is_external', e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 accent-brand" data-testid="doc-external" />
            <span>External doctor <span className="text-gray-500">— refers or prescribes but is not on staff (can have no clinic)</span></span>
          </label>
          {f.is_external && text('doc-hospital', 'Hospital / clinic they work at', 'hospital')}

          <div>
            <p className={labelCls}>Works at *</p>
            <ul className="border border-gray-200 rounded-lg divide-y" data-testid="doc-clinics">
              {clinics.map((c) => {
                const r = rows[c.clinic_id] || { on: false, fee: '' };
                return (
                  <li key={c.clinic_id} className="flex items-center gap-3 px-3 py-2">
                    <input id={`clinic-${c.clinic_id}`} type="checkbox" checked={r.on}
                      onChange={(e) => setRows((s) => ({ ...s, [c.clinic_id]: { ...r, on: e.target.checked } }))}
                      className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid={`clinic-on-${c.clinic_id}`} />
                    <label htmlFor={`clinic-${c.clinic_id}`} className="flex-1 text-sm text-gray-900">{c.clinic_name}</label>
                    <label htmlFor={`fee-${c.clinic_id}`} className="text-xs text-gray-500">Fee ₹</label>
                    <input id={`fee-${c.clinic_id}`} type="number" min="0" step="1" disabled={!r.on} value={r.fee}
                      onChange={(e) => setRows((s) => ({ ...s, [c.clinic_id]: { ...r, fee: e.target.value } }))}
                      placeholder="no fee" className="w-24 px-2 py-1 border border-gray-200 rounded-lg text-sm disabled:bg-gray-50"
                      data-testid={`clinic-fee-${c.clinic_id}`} aria-invalid={r.on && r.fee.trim() !== '' && !(Number(r.fee) >= 0)} />
                  </li>
                );
              })}
            </ul>
            <p className="text-xs text-gray-500 mt-1">The fee is added to the patient's bill at check-in, per clinic.</p>
          </div>

          <div>
            <label htmlFor="doc-login" className={labelCls}>Linked login (optional)</label>
            <Select value={login} onValueChange={setLogin}>
              <SelectTrigger id="doc-login" className="w-full" data-testid="doc-login">
                <SelectValue placeholder="No login" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_LOGIN}>No login</SelectItem>
                {loginOptions.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}{u.email ? ` · ${u.email}` : ''}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-500 mt-1">Logins are managed in Team. Link one only if this doctor signs in.</p>
          </div>

          <div>
            <label htmlFor="doc-notes" className={labelCls}>Notes</label>
            <textarea id="doc-notes" rows={2} value={f.notes} onChange={(e) => set('notes', e.target.value)}
              className={`${fieldCls} resize-none`} />
          </div>

          {doctor && (
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer" htmlFor="doc-active">
              <input id="doc-active" type="checkbox" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid="doc-active" />
              Active — can be booked and shown in lists
            </label>
          )}
        </div>
        <DialogFooter className="mt-6">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
          <AppButton onClick={submit} loading={busy} disabled={!canSave} data-testid="doc-save-btn">
            {doctor ? 'Save' : 'Add doctor'}
          </AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
