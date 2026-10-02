import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton, FilterPills } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { patientSchema, PatientFormValues } from '@/lib/schemas/patient';
import { useEmrSettings } from '../useEmrSettings';
import type { EmrPatient, FieldState, PatientFormField } from '../types';

const DEFAULTS: PatientFormValues = {
  name: '', phone: '', alternate_phone: '', age: '', date_of_birth: '',
  gender: '', blood_group: '', city: '', allergies: '', notes: '',
};

const GENDER_OPTIONS = [
  { key: 'male', label: 'Male' },
  { key: 'female', label: 'Female' },
  { key: 'other', label: 'Other' },
];

const cls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm aria-invalid:border-red-500 aria-invalid:focus:ring-red-500';

export interface PatientFormModalProps {
  open: boolean;
  /** Existing patient to edit; omit to register a new one. */
  patient?: EmrPatient | null;
  /** Pre-fills the name (e.g. what the receptionist already typed in a search). */
  initialName?: string;
  onClose: () => void;
  onSaved: (patient: EmrPatient) => void;
}

export default function PatientFormModal({ open, patient, initialName, onClose, onSaved }: PatientFormModalProps) {
  const { settings } = useEmrSettings(open);
  // Until settings load (or if they fail to), every field shows as optional — registration is never blocked.
  const state = (f: PatientFormField): FieldState => settings?.patient_form?.[f] || 'optional';
  const shown = (f: PatientFormField) => state(f) !== 'hidden';
  const star = (f: PatientFormField) => (state(f) === 'required' ? ' *' : '');
  const { register, handleSubmit, reset, watch, setValue, setError, formState: { errors, isSubmitting } } =
    useForm<PatientFormValues>({ resolver: zodResolver(patientSchema), defaultValues: DEFAULTS });

  useEffect(() => {
    reset(patient ? {
      name: patient.name, phone: patient.phone || '', alternate_phone: patient.alternate_phone || '',
      age: patient.age != null ? String(patient.age) : '', date_of_birth: patient.date_of_birth || '',
      gender: patient.gender || '', blood_group: patient.blood_group || '', city: patient.city || '',
      allergies: patient.allergies || '', notes: patient.notes || '',
    } : { ...DEFAULTS, name: initialName || '' });
  }, [patient, initialName, open, reset]);

  const onSubmit = async (v: PatientFormValues) => {
    const blank = (Object.keys(v) as (keyof PatientFormValues)[]).filter(
      (k) => k !== 'name' && state(k as PatientFormField) === 'required' && !String(v[k] ?? '').trim());
    if (blank.length) {
      blank.forEach((k) => setError(k, { type: 'required', message: 'This field is required' }));
      return;
    }
    const body = {
      name: v.name, phone: v.phone || null, alternate_phone: v.alternate_phone || null,
      age: v.age ? Number(v.age) : null, date_of_birth: v.date_of_birth || null,
      gender: v.gender || null, blood_group: v.blood_group || null, city: v.city || null,
      allergies: v.allergies || null, notes: v.notes || null,
    };
    try {
      const res = patient
        ? await api.put(apiUrl.emrPatient(patient.id), body)
        : await api.post(apiUrl.emrPatients(), body);
      toast.success(patient ? 'Patient updated' : 'Patient registered');
      onSaved(res.data);
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const err = (f: keyof PatientFormValues) => errors[f]?.message
    ? <p id={`${f}-error`} role="alert" className="text-xs text-red-500 mt-1">{errors[f]?.message}</p>
    : null;
  const label = (text: string, id: string) => (
    <label htmlFor={id} className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">{text}</label>
  );
  const field = (f: keyof PatientFormValues, text: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div>
      {label(text, `patient-${f}`)}
      <input id={`patient-${f}`} {...register(f)} {...props} aria-invalid={!!errors[f]}
        aria-describedby={errors[f] ? `${f}-error` : undefined} className={cls} data-testid={`patient-${f}-input`} />
      {err(f)}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle>{patient ? 'Edit Patient' : 'Register Patient'}</DialogTitle></DialogHeader>
        {patient?.uhid && <p className="text-xs text-gray-500 -mt-2 mb-2" data-testid="patient-uhid">Patient ID {patient.uhid}</p>}
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">{field('name', 'Patient Name *')}</div>
            {shown('phone') && field('phone', `Mobile${star('phone')}`, { placeholder: '9876543210', inputMode: 'numeric', autoComplete: 'off' })}
            {shown('alternate_phone') && field('alternate_phone', `Alternate Mobile${star('alternate_phone')}`, { inputMode: 'numeric', autoComplete: 'off' })}
            {shown('age') && field('age', `Age (years)${star('age')}`, { inputMode: 'numeric' })}
            {shown('date_of_birth') && field('date_of_birth', `Date of Birth${star('date_of_birth')}`, { type: 'date' })}
            {shown('gender') && (
              <div>
                {label(`Gender${star('gender')}`, 'patient-gender')}
                <FilterPills options={GENDER_OPTIONS} active={watch('gender')}
                  onChange={(k) => setValue('gender', k, { shouldDirty: true })} />
                {err('gender')}
              </div>
            )}
            {shown('blood_group') && field('blood_group', `Blood Group${star('blood_group')}`, { placeholder: 'e.g. B+' })}
            {shown('city') && field('city', `City${star('city')}`)}
            {shown('allergies') && <div className="col-span-2">
              {label(`Allergies${star('allergies')}`, 'patient-allergies')}
              <textarea id="patient-allergies" {...register('allergies')} rows={2} placeholder="e.g. Penicillin, sulfa drugs"
                className={`${cls} resize-none`} data-testid="patient-allergies-input" />
              {err('allergies')}
            </div>}
            {shown('notes') && <div className="col-span-2">
              {label(`Notes${star('notes')}`, 'patient-notes')}
              <textarea id="patient-notes" {...register('notes')} rows={2} className={`${cls} resize-none`} />
              {err('notes')}
            </div>}
          </div>
          <DialogFooter className="mt-6">
            <AppButton type="button" variant="secondary" onClick={onClose} disabled={isSubmitting}>Cancel</AppButton>
            <AppButton type="submit" loading={isSubmitting} data-testid="submit-patient-btn">
              {patient ? 'Update' : 'Register'}
            </AppButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
