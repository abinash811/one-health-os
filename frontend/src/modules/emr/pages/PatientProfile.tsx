/**
 * EMR Patient profile — one page per patient: details, allergies, and every
 * visit with its prescription. Route: /emr/patients/:patientId.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { CalendarPlus, ChevronLeft, Pencil, History } from 'lucide-react';
import { PageHeader, DataCard, AppButton, EmptyState, ErrorState, TableSkeleton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { ROUTES } from '@/constants/routes';
import { formatDate } from '@/utils/dates';
import PatientFormModal from '../components/PatientFormModal';
import BookAppointmentModal from '../components/BookAppointmentModal';
import VisitTimeline from '../components/VisitTimeline';
import type { EmrAppointment, EmrDoctor, EmrPatient, EmrPrescription } from '../types';

const labelCls = 'text-xs font-bold text-gray-500 uppercase tracking-wide';

const Fact = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div><p className={labelCls}>{label}</p><p className="text-sm text-gray-900">{value || '—'}</p></div>
);

export default function PatientProfile() {
  const { patientId = '' } = useParams();
  const navigate = useNavigate();
  const [patient, setPatient] = useState<EmrPatient | null>(null);
  const [error, setError] = useState('');
  const [visits, setVisits] = useState<EmrAppointment[]>([]);
  const [rxs, setRxs] = useState<EmrPrescription[]>([]);
  const [doctors, setDoctors] = useState<EmrDoctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [bookOpen, setBookOpen] = useState(false);

  const [tick, setTick] = useState(0);
  // Bumping `tick` re-runs the load below; the first load starts with loading=true.
  const reload = () => { setLoading(true); setError(''); setTick((t) => t + 1); };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await api.get(apiUrl.emrPatient(patientId));
        if (!cancelled) setPatient(p.data);
      } catch (err) {
        if (!cancelled) { setError((err as Error).message); setLoading(false); }
        return;
      }
      // Visits and prescriptions are separate permissions — a failure of one still shows the other.
      const [v, r, d] = await Promise.allSettled([
        api.get(apiUrl.emrAppointments({ patient_id: patientId })),
        api.get(apiUrl.emrPatientPrescriptions(patientId)),
        api.get(apiUrl.emrDoctors()),
      ]);
      if (cancelled) return;
      if (v.status === 'fulfilled') setVisits(v.value.data || []); else toast.error((v.reason as Error).message);
      if (r.status === 'fulfilled') setRxs(r.value.data || []); else toast.error((r.reason as Error).message);
      if (d.status === 'fulfilled') setDoctors(d.value.data || []);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [patientId, tick]);

  if (error) {
    return (
      <div className="px-8 py-6 min-h-screen bg-page">
        <PageHeader title="Patient" />
        <DataCard><ErrorState message={error} onRetry={reload} /></DataCard>
      </div>
    );
  }

  const p = patient;
  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-patient-profile">
      <PageHeader
        title={p?.name || 'Patient'}
        breadcrumb={(
          <AppButton variant="chip" icon={<ChevronLeft className="w-4 h-4" />}
            onClick={() => navigate(ROUTES.EMR.PATIENTS)}>All patients</AppButton>
        )}
        actions={p && (
          <>
            <AppButton variant="outline" icon={<Pencil className="w-4 h-4" />} onClick={() => setEditOpen(true)}
              data-testid="edit-profile-btn">Edit</AppButton>
            <AppButton icon={<CalendarPlus className="w-4 h-4" />} onClick={() => setBookOpen(true)}
              data-testid="book-for-patient-btn">Book Appointment</AppButton>
          </>
        )}
      />

      {!p ? <DataCard noPadding><TableSkeleton rows={4} columns={4} /></DataCard> : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <DataCard noPadding={false}>
            {p.allergies && (
              <p className="mb-4 px-3 py-2 rounded bg-red-50 text-red-700 text-sm font-medium" data-testid="profile-allergies">
                Allergies: {p.allergies}
              </p>
            )}
            <div className="grid grid-cols-2 gap-4">
              <Fact label="Patient ID (UHID)" value={p.uhid} />
              <Fact label="Age" value={p.age != null ? `${p.age} yrs` : null} />
              <Fact label="Gender" value={p.gender} />
              <Fact label="Mobile" value={p.phone} />
              <Fact label="Blood group" value={p.blood_group} />
              <Fact label="Email" value={p.email} />
              <Fact label="City" value={p.city} />
              <div className="col-span-2"><Fact label="Address" value={p.address} /></div>
              <div className="col-span-2"><Fact label="Notes" value={p.notes} /></div>
              <Fact label="Visits" value={String(visits.length)} />
              <Fact label="Last visit" value={visits[0] ? formatDate(visits[0].appointment_date) : null} />
            </div>
          </DataCard>

          <div className="xl:col-span-2">
            <DataCard noPadding>
              <div className="px-4 py-3 border-b"><span className={labelCls}>Visit history</span></div>
              {loading ? <TableSkeleton rows={4} columns={3} /> : visits.length === 0 ? (
                <EmptyState icon={History} title="No visits yet"
                  description="Book an appointment to start this patient's history."
                  action={<AppButton onClick={() => setBookOpen(true)}>Book Appointment</AppButton>} />
              ) : (
                <VisitTimeline appointments={visits} prescriptions={rxs} onOpen={navigate} />
              )}
            </DataCard>
          </div>
        </div>
      )}

      <PatientFormModal open={editOpen} patient={p} onClose={() => setEditOpen(false)} onSaved={reload} />
      <BookAppointmentModal open={bookOpen} doctors={doctors} defaultPatient={p}
        onClose={() => setBookOpen(false)} onBooked={reload} />
    </div>
  );
}
