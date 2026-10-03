/**
 * EMR Calendar — the Practo-style schedule: doctors side by side for a day, or one doctor's week.
 * Route: /emr/calendar. Click an open slot to book, click a visit for its actions, drag a booked
 * visit onto another open slot to reschedule. Same data as the Appointments queue, drawn on a grid.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react';
import { PageHeader, PageTabs, DataCard, TableSkeleton, AppButton, EmptyState, FilterPills } from '@/components/shared';
import { useClinicAccess } from '@/utils/clinicAccess';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { APPOINTMENT_STATUS } from '@/constants/domainConstants';
import { ROUTES } from '@/constants/routes';
import { today } from '@/utils/dates';
import CollectPaymentDialog from '@/modules/patient_billing/components/CollectPaymentDialog';
import { EMR_TABS, emrTabRoute } from '../emrTabs';
import { addDays, buildColumns, dayLabel, isLive, STATUS_LEGEND, STATUS_CARD, toHHMM, visibleRange, weekDates, type CalColumn, type CalendarView, type Slot } from '../calendarUtils';
import { useCalendarData } from '../useCalendarData';
import { to12h } from '../timeFormat';
import AppointmentDetailDialog from '../components/AppointmentDetailDialog';
import BookAppointmentModal from '../components/BookAppointmentModal';
import CalendarGrid from '../components/CalendarGrid';
import CancelAppointmentDialog from '../components/CancelAppointmentDialog';
import DoctorSelect, { ALL_DOCTORS } from '../components/DoctorSelect';
import type { EmrAppointment } from '../types';

const VIEWS = [{ key: 'day', label: 'Day' }, { key: 'week', label: 'Week' }];
const minutesNow = () => { const n = new Date(); return n.getHours() * 60 + n.getMinutes(); };

interface Booking { doctorId: string; date: string; time: string }

export default function Calendar() {
  const navigate = useNavigate();
  const [view, setView] = useState<CalendarView>('day');
  const [date, setDate] = useState<string>(today());
  const [doctorPick, setDoctorPick] = useState(ALL_DOCTORS);
  const [nowMin, setNowMin] = useState(minutesNow);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [bookOpen, setBookOpen] = useState(false);
  const [selected, setSelected] = useState<EmrAppointment | null>(null);
  const [cancelling, setCancelling] = useState<EmrAppointment | null>(null);
  const [collecting, setCollecting] = useState<EmrAppointment | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const { canCollect, canWriteRx } = useClinicAccess();

  const dates = view === 'week' ? weekDates(date) : [date];
  const from = dates[0];
  const to = dates[dates.length - 1];
  // A week belongs to one doctor, so "All doctors" falls back to the first.
  const { doctors, schedules, appointments, loading, reload } = useCalendarData(
    from, to, view === 'day' ? (doctorPick === ALL_DOCTORS ? undefined : doctorPick) : undefined);
  const doctorId = doctorPick === ALL_DOCTORS && view === 'week' ? doctors[0]?.id || '' : doctorPick;

  useEffect(() => {
    const timer = setInterval(() => setNowMin(minutesNow()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const columns = useMemo(() => buildColumns(
    view, date, view === 'day' && doctorId !== ALL_DOCTORS ? doctors.filter((d) => d.id === doctorId) : doctors, doctorId,
  ), [view, date, doctors, doctorId]);
  const live = useMemo(() => appointments.filter(isLive)
    .filter((a) => view === 'day' || a.doctor_user_id === doctorId), [appointments, view, doctorId]);
  const range = useMemo(() => visibleRange(columns, schedules, live), [columns, schedules, live]);

  const step = view === 'week' ? 7 : 1;
  const title = view === 'week' ? `${dayLabel(from)} – ${dayLabel(to)}` : dayLabel(date);

  const openSlot = (col: CalColumn, slot: Slot) => {
    setBooking({ doctorId: col.doctorId, date: col.date, time: toHHMM(slot.start) });
    setBookOpen(true);
  };

  const moveVisit = async (a: EmrAppointment, col: CalColumn, slot: Slot) => {
    const start = toHHMM(slot.start);
    if (a.doctor_user_id === col.doctorId && a.appointment_date === col.date && a.start_time === start) return;
    try {
      await api.put(apiUrl.emrAppointment(a.id), { appointment_date: col.date, start_time: start, doctor_user_id: col.doctorId });
      toast.success(`${a.patient_name || 'Visit'} moved to ${to12h(start)}`);
    } catch (err) {
      toast.error((err as Error).message);
    }
    reload(false);
  };

  const changeStatus = async (a: EmrAppointment, next: string) => {
    setBusyId(a.id);
    try {
      await api.post(apiUrl.emrAppointmentStatus(a.id), { status: next });
      setSelected(null);
      if (next === APPOINTMENT_STATUS.IN_CONSULT && canWriteRx) { navigate(ROUTES.EMR.CONSULT(a.id)); return; }
      reload(false);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-calendar-page">
      <PageHeader title="Clinic" actions={(
        <AppButton icon={<CalendarPlus className="w-4 h-4" />} onClick={() => { setBooking(null); setBookOpen(true); }} data-testid="book-appointment-btn">
          Book Appointment
        </AppButton>
      )} />
      <PageTabs tabs={EMR_TABS} activeTab="calendar" onChange={(k) => navigate(emrTabRoute(k))} />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-1">
          <AppButton variant="outline" size="sm" iconOnly icon={<ChevronLeft className="w-4 h-4" />} aria-label={`Previous ${view}`}
            onClick={() => setDate(addDays(date, -step))} />
          <AppButton variant="outline" size="sm" iconOnly icon={<ChevronRight className="w-4 h-4" />} aria-label={`Next ${view}`}
            onClick={() => setDate(addDays(date, step))} />
          <AppButton variant="ghost" size="sm" onClick={() => setDate(today())}>Today</AppButton>
        </div>
        <h2 className="text-base font-semibold text-gray-900 min-w-[150px]" data-testid="calendar-title">{title}</h2>
        <FilterPills options={VIEWS} active={view} onChange={(k) => setView(k as CalendarView)} />
        <DoctorSelect doctors={doctors} value={doctorId} onChange={setDoctorPick} allowAll={view === 'day'} testId="calendar-doctor-filter" />
        <div className="flex items-center gap-3 ml-auto text-xs text-gray-600">
          {STATUS_LEGEND.map((l) => (
            <span key={l.status} className="inline-flex items-center gap-1">
              <span className={`w-3 h-3 rounded border ${STATUS_CARD[l.status]}`} />{l.label}
            </span>
          ))}
        </div>
      </div>

      {loading ? (
        <DataCard noPadding><TableSkeleton rows={8} columns={4} /></DataCard>
      ) : columns.length === 0 ? (
        <DataCard><EmptyState title="No doctors yet" description="Add a doctor under Settings, then set their working hours in Doctor Schedules." /></DataCard>
      ) : (
        <CalendarGrid columns={columns} schedules={schedules} appointments={live} range={range}
          todayISO={today()} nowMin={nowMin} onSlotClick={openSlot} onOpen={setSelected} onMove={moveVisit} />
      )}

      <BookAppointmentModal open={bookOpen} doctors={doctors}
        defaultDoctorId={booking?.doctorId || (doctorId === ALL_DOCTORS ? undefined : doctorId)}
        defaultDate={booking?.date} defaultStartTime={booking?.time}
        onClose={() => setBookOpen(false)} onBooked={() => reload(false)} />
      <AppointmentDetailDialog appointment={selected} busy={busyId === selected?.id} onClose={() => setSelected(null)}
        onMove={changeStatus} onCancel={(a) => { setSelected(null); setCancelling(a); }}
        onOpenRx={(a) => navigate(ROUTES.EMR.CONSULT(a.id))} canWriteRx={canWriteRx}
        onCollect={canCollect ? (a) => { setSelected(null); setCollecting(a); } : undefined}
        onPrintReceipt={(a) => a.fee?.invoice_id && navigate(ROUTES.PATIENT_BILLING.INVOICE_PRINT(a.fee.invoice_id))}
        onOpenPatient={(a) => navigate(ROUTES.EMR.PATIENT(a.patient_id))} />
      {collecting?.fee && (
        <CollectPaymentDialog open patientId={collecting.patient_id} patientName={collecting.patient_name || 'Patient'}
          charges={collecting.fee.invoice_id ? [] : [{ id: collecting.fee.charge_id, total_paise: collecting.fee.amount_paise,
            description: `Consultation — ${collecting.doctor_name || 'Doctor'}` }]}
          existingInvoice={collecting.fee.invoice_id ? { id: collecting.fee.invoice_id,
            invoice_number: collecting.fee.invoice_number || '', balance_paise: collecting.fee.balance_paise } : null}
          onClose={() => setCollecting(null)} onCollected={() => reload(false)} />
      )}
      <CancelAppointmentDialog appointment={cancelling} onClose={() => setCancelling(null)} onCancelled={() => reload(false)} />
    </div>
  );
}
