/**
 * EMR Appointments — the receptionist's day view and live queue.
 * Route: /emr/appointments (docs/28_EMR_SCOPE.md). Refreshes itself every
 * 30s so a check-in at the front desk shows up at the doctor's screen.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { CalendarDays, CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  PageHeader, PageTabs, DataCard, TableSkeleton, AppButton, EmptyState, FilterPills, StatusBadge,
} from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { APPOINTMENT_STATUS, APPOINTMENT_TYPE } from '@/constants/domainConstants';
import { formatDate, today } from '@/utils/dates';
import { ROUTES } from '@/constants/routes';
import { EMR_TABS, emrTabRoute } from '../emrTabs';
import { to12h } from '../timeFormat';
import BookAppointmentModal from '../components/BookAppointmentModal';
import CancelAppointmentDialog from '../components/CancelAppointmentDialog';
import DoctorSelect, { ALL_DOCTORS } from '../components/DoctorSelect';
import QueueActions from '../components/QueueActions';
import type { EmrAppointment, EmrDoctor } from '../types';

const REFRESH_MS = 30_000;
const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';

const STATUS_FILTERS = [
  { key: 'all', label: 'All' },
  { key: APPOINTMENT_STATUS.BOOKED, label: 'Booked' },
  { key: APPOINTMENT_STATUS.CHECKED_IN, label: 'Waiting' },
  { key: APPOINTMENT_STATUS.IN_CONSULT, label: 'In consult' },
  { key: APPOINTMENT_STATUS.COMPLETED, label: 'Done' },
  { key: APPOINTMENT_STATUS.CANCELLED, label: 'Cancelled' },
];

const shiftDay = (iso: string, days: number): string => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export default function Appointments() {
  const navigate = useNavigate();
  const [date, setDate] = useState<string>(today());
  const [doctorId, setDoctorId] = useState(ALL_DOCTORS);
  const [status, setStatus] = useState('all');
  const [doctors, setDoctors] = useState<EmrDoctor[]>([]);
  const [rows, setRows] = useState<EmrAppointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bookOpen, setBookOpen] = useState(false);
  const [cancelling, setCancelling] = useState<EmrAppointment | null>(null);

  useEffect(() => {
    api.get(apiUrl.emrDoctors()).then((res: { data: EmrDoctor[] }) => setDoctors(res.data || []))
      .catch((err: Error) => toast.error(err.message));
  }, []);

  const fetchQueue = useCallback(async (showSkeleton: boolean) => {
    if (showSkeleton) setLoading(true);
    try {
      const res = await api.get(apiUrl.emrAppointments({
        date,
        doctor_user_id: doctorId === ALL_DOCTORS ? undefined : doctorId,
        status: status === 'all' ? undefined : status,
      }));
      setRows(res.data || []);
    } catch (err) {
      if (showSkeleton) toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [date, doctorId, status]);

  useEffect(() => {
    fetchQueue(true);
    const timer = setInterval(() => fetchQueue(false), REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchQueue]);

  const move = async (a: EmrAppointment, next: string) => {
    setBusyId(a.id);
    try {
      await api.post(apiUrl.emrAppointmentStatus(a.id), { status: next });
      // Starting a consult goes straight to the prescription — one click, not two.
      if (next === APPOINTMENT_STATUS.IN_CONSULT) { navigate(ROUTES.EMR.CONSULT(a.id)); return; }
      fetchQueue(false);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-appointments-page">
      <PageHeader
        title="Clinic"
        actions={(
          <AppButton icon={<CalendarPlus className="w-4 h-4" />} onClick={() => setBookOpen(true)} data-testid="book-appointment-btn">
            Book Appointment
          </AppButton>
        )}
      />
      <PageTabs tabs={EMR_TABS} activeTab="appointments" onChange={(k) => navigate(emrTabRoute(k))} />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-1">
          <AppButton variant="outline" size="sm" iconOnly icon={<ChevronLeft className="w-4 h-4" />}
            aria-label="Previous day" onClick={() => setDate(shiftDay(date, -1))} />
          <input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)}
            aria-label="Appointment date" data-testid="queue-date-input"
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand" />
          <AppButton variant="outline" size="sm" iconOnly icon={<ChevronRight className="w-4 h-4" />}
            aria-label="Next day" onClick={() => setDate(shiftDay(date, 1))} />
          {date !== today() && <AppButton variant="ghost" size="sm" onClick={() => setDate(today())}>Today</AppButton>}
        </div>
        <DoctorSelect doctors={doctors} value={doctorId} onChange={setDoctorId} allowAll testId="queue-doctor-filter" />
        <FilterPills options={STATUS_FILTERS} active={status} onChange={setStatus} />
      </div>

      <DataCard noPadding>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="queue-table">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className={TH}>Token</th>
                <th className={TH}>Time</th>
                <th className={TH}>Patient</th>
                <th className={TH}>Doctor</th>
                <th className={TH}>Reason</th>
                <th className={TH}>Status</th>
                <th className={`${TH} text-right`}>Next step</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr><td colSpan={7} className="p-0"><TableSkeleton rows={6} columns={7} /></td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={7}>
                  <EmptyState icon={CalendarDays}
                    title={`No appointments on ${formatDate(date)}`}
                    description="Book one, or issue a walk-in token for today."
                    action={<AppButton onClick={() => setBookOpen(true)}>Book Appointment</AppButton>} />
                </td></tr>
              ) : rows.map((a) => (
                <tr key={a.id} className="hover:bg-brand-tint transition-colors" data-testid={`queue-row-${a.id}`}>
                  <td className="px-4 py-3 font-mono font-semibold text-gray-900">#{a.token_number}</td>
                  <td className="px-4 py-3 text-gray-700 whitespace-nowrap">
                    {a.appointment_type === APPOINTMENT_TYPE.WALK_IN ? 'Walk-in' : to12h(a.start_time)}
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{a.patient_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-700">{a.doctor_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-700 max-w-[220px] truncate" title={a.reason || a.cancel_reason || undefined}>
                    {a.cancel_reason ? `Cancelled: ${a.cancel_reason}` : a.reason || '—'}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
                  <td className="px-4 py-3">
                    <QueueActions appointment={a} busy={busyId === a.id} onMove={move} onCancel={setCancelling}
                      onOpenRx={(x) => navigate(ROUTES.EMR.CONSULT(x.id))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataCard>

      <BookAppointmentModal open={bookOpen} doctors={doctors}
        defaultDoctorId={doctorId === ALL_DOCTORS ? undefined : doctorId}
        onClose={() => setBookOpen(false)} onBooked={() => fetchQueue(false)} />
      <CancelAppointmentDialog appointment={cancelling} onClose={() => setCancelling(null)}
        onCancelled={() => fetchQueue(false)} />
    </div>
  );
}
