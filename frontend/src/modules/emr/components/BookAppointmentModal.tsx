import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton, FilterPills, SearchInput } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { today } from '@/utils/dates';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import PatientFormModal from './PatientFormModal';
import DoctorSelect from './DoctorSelect';
import { to12h } from '../timeFormat';
import type { EmrDoctor, EmrPatient, EmrSlot } from '../types';

const MODES = [
  { key: 'slot', label: 'Pick a time slot' },
  { key: 'walk_in', label: 'Walk-in (today)' },
];

const fieldCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';

export interface BookAppointmentModalProps {
  open: boolean;
  doctors: EmrDoctor[];
  /** Pre-selects this doctor (the day view's current filter). */
  defaultDoctorId?: string;
  onClose: () => void;
  onBooked: () => void;
}

export default function BookAppointmentModal({ open, doctors, defaultDoctorId, onClose, onBooked }: BookAppointmentModalProps) {
  const [patientQuery, setPatientQuery] = useState('');
  const [matches, setMatches] = useState<EmrPatient[]>([]);
  const [patient, setPatient] = useState<EmrPatient | null>(null);
  const [doctorId, setDoctorId] = useState('');
  const [date, setDate] = useState(today());
  const [mode, setMode] = useState('slot');
  const [slots, setSlots] = useState<EmrSlot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [startTime, setStartTime] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [newPatientOpen, setNewPatientOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPatientQuery(''); setMatches([]); setPatient(null); setDate(today()); setMode('slot');
    setStartTime(''); setReason('');
    setDoctorId(defaultDoctorId || doctors[0]?.id || '');
  }, [open, defaultDoctorId, doctors]);

  const searchPatients = useDebouncedCallback(async (q: string) => {
    if (!q.trim()) { setMatches([]); return; }
    try {
      const res = await api.get(apiUrl.emrPatients({ search: q, page_size: 6 }));
      setMatches(res.data.data || []);
    } catch (err) {
      toast.error((err as Error).message);
    }
  }, 250);

  useEffect(() => {
    if (!open || mode !== 'slot' || !doctorId || !date) { setSlots([]); return; }
    let cancelled = false;
    setSlotsLoading(true);
    setStartTime('');
    api.get(apiUrl.emrSlots({ doctor_user_id: doctorId, date }))
      .then((res) => { if (!cancelled) setSlots(res.data || []); })
      .catch((err: Error) => { if (!cancelled) toast.error(err.message); })
      .finally(() => { if (!cancelled) setSlotsLoading(false); });
    return () => { cancelled = true; };
  }, [open, mode, doctorId, date]);

  const walkIn = mode === 'walk_in';
  const canSubmit = !!patient && !!doctorId && (walkIn || !!startTime);

  const submit = async () => {
    if (!patient) return;
    setBusy(true);
    try {
      const res = await api.post(apiUrl.emrAppointments(), {
        patient_id: patient.id, doctor_user_id: doctorId,
        appointment_date: walkIn ? today() : date,
        start_time: walkIn ? undefined : startTime,
        reason: reason.trim() || undefined,
      });
      toast.success(walkIn ? `Token ${res.data.token_number} issued to ${patient.name}` : `Booked for ${to12h(startTime)}`);
      onBooked();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>Book appointment</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label htmlFor="appt-patient-search" className={labelCls}>Patient *</label>
              {patient ? (
                <div className="flex items-center justify-between px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
                  <span className="text-sm font-medium text-gray-900" data-testid="selected-patient">
                    {patient.name}{patient.phone ? ` · ${patient.phone}` : ''}
                  </span>
                  <AppButton variant="ghost" size="sm" onClick={() => setPatient(null)}>Change</AppButton>
                </div>
              ) : (
                <>
                  <SearchInput id="appt-patient-search" value={patientQuery} placeholder="Search by name or mobile"
                    onChange={(v) => { setPatientQuery(v); searchPatients(v); }} />
                  {matches.length > 0 && (
                    <ul className="mt-1 border border-gray-200 rounded-lg divide-y max-h-40 overflow-y-auto" data-testid="patient-matches">
                      {matches.map((m) => (
                        <li key={m.id}>
                          <AppButton variant="ghost" className="w-full justify-start rounded-none" onClick={() => setPatient(m)}
                            data-testid={`pick-patient-${m.id}`}>
                            {m.name}{m.phone ? ` · ${m.phone}` : ''}
                          </AppButton>
                        </li>
                      ))}
                    </ul>
                  )}
                  {patientQuery.trim() && matches.length === 0 && (
                    <p className="text-xs text-gray-500 mt-1">No match.</p>
                  )}
                  <AppButton variant="ghost" size="sm" className="mt-1" onClick={() => setNewPatientOpen(true)}
                    data-testid="new-patient-btn">
                    + Register a new patient
                  </AppButton>
                </>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="appt-doctor" className={labelCls}>Doctor *</label>
                <DoctorSelect id="appt-doctor" doctors={doctors} value={doctorId} onChange={setDoctorId}
                  className="w-full" testId="appt-doctor-select" />
              </div>
              <div>
                <label htmlFor="appt-date" className={labelCls}>Date</label>
                <input id="appt-date" type="date" min={today()} value={walkIn ? today() : date} disabled={walkIn}
                  onChange={(e) => setDate(e.target.value)} className={fieldCls} data-testid="appt-date-input" />
              </div>
            </div>

            <FilterPills options={MODES} active={mode} onChange={setMode} />

            {!walkIn && (
              <div data-testid="slot-grid">
                {slotsLoading ? (
                  <p className="text-sm text-gray-500">Loading slots…</p>
                ) : slots.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    This doctor has no working hours on that day. Add them under Doctor Schedules, or choose Walk-in.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {slots.map((s) => (
                      <AppButton key={s.start_time} size="sm" disabled={!s.available}
                        variant={startTime === s.start_time ? 'primary' : 'outline'}
                        onClick={() => setStartTime(s.start_time)} data-testid={`slot-${s.start_time}`}>
                        {to12h(s.start_time)}
                      </AppButton>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <label htmlFor="appt-reason" className={labelCls}>Reason for visit</label>
              <textarea id="appt-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                className={`${fieldCls} resize-none`} />
            </div>
          </div>
          <DialogFooter className="mt-6">
            <AppButton variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
            <AppButton onClick={submit} loading={busy} disabled={!canSubmit} data-testid="submit-appointment-btn">
              {walkIn ? 'Issue token' : 'Book appointment'}
            </AppButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PatientFormModal open={newPatientOpen} initialName={patientQuery} onClose={() => setNewPatientOpen(false)}
        onSaved={(p) => { setPatient(p); setMatches([]); }} />
    </>
  );
}
