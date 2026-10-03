/** Pure helpers for the calendar: time maths, the week's dates, slot grids from the doctor's schedule. */
import { APPOINTMENT_STATUS } from '@/constants/domainConstants';
import type { EmrAppointment, EmrDoctor, EmrScheduleBlock } from './types';

/** Height of one minute on screen — a 15-minute slot is 24px, a 30-minute slot 48px. */
export const PX_PER_MIN = 1.6;
const DEFAULT_START = 8 * 60;
const DEFAULT_END = 20 * 60;
const FALLBACK_VISIT_MIN = 15;

export type CalendarView = 'day' | 'week';

export interface CalColumn {
  key: string;
  date: string;
  doctorId: string;
  title: string;
  subtitle: string;
}
export interface Slot { start: number; end: number }

export const toMinutes = (hhmm: string): number => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};
export const toHHMM = (min: number): string =>
  `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

const parse = (iso: string): Date => new Date(`${iso}T00:00:00`);
const fmtISO = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export const addDays = (iso: string, n: number): string => {
  const d = parse(iso);
  d.setDate(d.getDate() + n);
  return fmtISO(d);
};
/** Monday = 0 … Sunday = 6, the same numbering the schedule blocks use. */
export const weekdayOf = (iso: string): number => (parse(iso).getDay() + 6) % 7;
export const weekDates = (iso: string): string[] => {
  const monday = addDays(iso, -weekdayOf(iso));
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
};
export const dayLabel = (iso: string): string =>
  parse(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

export const isLive = (a: EmrAppointment): boolean =>
  a.status !== APPOINTMENT_STATUS.CANCELLED && a.status !== APPOINTMENT_STATUS.NO_SHOW;

const blocksFor = (schedules: EmrScheduleBlock[], doctorId: string, date: string) =>
  schedules.filter((b) => b.doctor_user_id === doctorId && b.is_active && b.weekday === weekdayOf(date));

/** Every bookable slot the doctor works on `date`, in minutes from midnight. */
export const slotsFor = (schedules: EmrScheduleBlock[], doctorId: string, date: string): Slot[] => {
  const slots: Slot[] = [];
  blocksFor(schedules, doctorId, date).forEach((b) => {
    const stop = toMinutes(b.end_time);
    for (let cur = toMinutes(b.start_time); cur + b.slot_minutes <= stop; cur += b.slot_minutes) {
      slots.push({ start: cur, end: cur + b.slot_minutes });
    }
  });
  return slots.sort((a, b) => a.start - b.start);
};

/** The doctor's working-hour stretches on `date` (drawn white; everything else is greyed out). */
export const workingRanges = (schedules: EmrScheduleBlock[], doctorId: string, date: string): Slot[] =>
  blocksFor(schedules, doctorId, date).map((b) => ({ start: toMinutes(b.start_time), end: toMinutes(b.end_time) }));

/** Columns: one per doctor for a day, or one per weekday for a single doctor's week. */
export function buildColumns(view: CalendarView, date: string, doctors: EmrDoctor[], doctorId: string): CalColumn[] {
  if (view === 'week') {
    const doc = doctors.find((d) => d.id === doctorId);
    return weekDates(date).map((d) => ({ key: d, date: d, doctorId, title: dayLabel(d), subtitle: doc?.name || '' }));
  }
  return doctors.map((d) => ({ key: d.id, date, doctorId: d.id, title: d.name, subtitle: dayLabel(date) }));
}

/** Visible hours: cover every working block and booked visit, rounded out to whole hours. */
export function visibleRange(cols: CalColumn[], schedules: EmrScheduleBlock[], appts: EmrAppointment[]): Slot {
  const mins: number[] = [];
  cols.forEach((c) => workingRanges(schedules, c.doctorId, c.date).forEach((r) => mins.push(r.start, r.end)));
  appts.forEach((a) => {
    if (!a.start_time) return;
    mins.push(toMinutes(a.start_time), a.end_time ? toMinutes(a.end_time) : toMinutes(a.start_time) + FALLBACK_VISIT_MIN);
  });
  if (!mins.length) return { start: DEFAULT_START, end: DEFAULT_END };
  return { start: Math.floor(Math.min(...mins) / 60) * 60, end: Math.ceil(Math.max(...mins) / 60) * 60 };
}

/** Card colours per visit status — same families as StatusBadge so the two never disagree. */
export const STATUS_CARD: Record<string, string> = {
  [APPOINTMENT_STATUS.BOOKED]: 'bg-blue-50 border-blue-300 text-blue-800 hover:text-blue-800',
  [APPOINTMENT_STATUS.CHECKED_IN]: 'bg-amber-50 border-amber-300 text-amber-800 hover:text-amber-800',
  [APPOINTMENT_STATUS.IN_CONSULT]: 'bg-purple-50 border-purple-300 text-purple-800 hover:text-purple-800',
  [APPOINTMENT_STATUS.COMPLETED]: 'bg-green-50 border-green-300 text-green-800 hover:text-green-800',
};

export const STATUS_LEGEND = [
  { status: APPOINTMENT_STATUS.BOOKED, label: 'Booked' },
  { status: APPOINTMENT_STATUS.CHECKED_IN, label: 'Waiting' },
  { status: APPOINTMENT_STATUS.IN_CONSULT, label: 'In consult' },
  { status: APPOINTMENT_STATUS.COMPLETED, label: 'Done' },
];
