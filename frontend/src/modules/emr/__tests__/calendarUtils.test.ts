import {
  addDays, buildColumns, isLive, slotsFor, toHHMM, toMinutes, visibleRange, weekDates, weekdayOf, workingRanges,
} from '../calendarUtils';
import type { EmrAppointment, EmrScheduleBlock } from '../types';

// 2026-10-05 is a Monday.
const MON = '2026-10-05';
const block = (over: Partial<EmrScheduleBlock>): EmrScheduleBlock => ({
  id: 'b', doctor_user_id: 'd1', weekday: 0, start_time: '09:00', end_time: '10:00', slot_minutes: 30, is_active: true, ...over,
});
const appt = (over: Partial<EmrAppointment>): EmrAppointment => ({
  id: 'a', patient_id: 'p', patient_name: 'P', doctor_user_id: 'd1', doctor_name: 'D', appointment_date: MON,
  start_time: '09:00', end_time: '09:30', token_number: 1, appointment_type: 'scheduled', status: 'booked',
  reason: null, cancel_reason: null, ...over,
});

describe('calendarUtils', () => {
  it('converts times both ways', () => {
    expect(toMinutes('09:30')).toBe(570);
    expect(toHHMM(570)).toBe('09:30');
    expect(toHHMM(0)).toBe('00:00');
  });

  it('numbers weekdays Monday=0 like the schedule blocks', () => {
    expect(weekdayOf(MON)).toBe(0);
    expect(weekdayOf('2026-10-11')).toBe(6);
  });

  it('builds a Monday-to-Sunday week from any day, across month ends', () => {
    expect(weekDates('2026-10-08')[0]).toBe(MON);
    expect(weekDates('2026-10-08')[6]).toBe('2026-10-11');
    expect(weekDates('2026-11-01')[0]).toBe('2026-10-26');
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
  });

  it('makes slots from the doctor\'s active blocks for that weekday only', () => {
    const blocks = [block({}), block({ id: 'x', weekday: 1 }), block({ id: 'y', is_active: false, start_time: '14:00', end_time: '15:00' })];
    expect(slotsFor(blocks, 'd1', MON)).toEqual([{ start: 540, end: 570 }, { start: 570, end: 600 }]);
    expect(slotsFor(blocks, 'other', MON)).toEqual([]);
    expect(workingRanges(blocks, 'd1', MON)).toEqual([{ start: 540, end: 600 }]);
  });

  it('drops a trailing partial slot', () => {
    expect(slotsFor([block({ end_time: '09:45' })], 'd1', MON)).toHaveLength(1);
  });

  it('hides cancelled and no-show visits', () => {
    expect(isLive(appt({ status: 'booked' }))).toBe(true);
    expect(isLive(appt({ status: 'cancelled' }))).toBe(false);
    expect(isLive(appt({ status: 'no_show' }))).toBe(false);
  });

  it('makes day columns per doctor and week columns per day', () => {
    const docs = [{ id: 'd1', name: 'Dr A', role: 'doctor' }, { id: 'd2', name: 'Dr B', role: 'doctor' }];
    expect(buildColumns('day', MON, docs, 'all').map((c) => c.doctorId)).toEqual(['d1', 'd2']);
    const week = buildColumns('week', MON, docs, 'd2');
    expect(week).toHaveLength(7);
    expect(week.every((c) => c.doctorId === 'd2')).toBe(true);
  });

  it('shows 8 AM–8 PM when nothing is scheduled, else the hours that matter', () => {
    const cols = buildColumns('day', MON, [{ id: 'd1', name: 'Dr A', role: 'doctor' }], 'd1');
    expect(visibleRange(cols, [], [])).toEqual({ start: 480, end: 1200 });
    expect(visibleRange(cols, [block({ start_time: '09:30', end_time: '12:15' })], [])).toEqual({ start: 540, end: 780 });
    // a visit outside the schedule still has to be visible
    expect(visibleRange(cols, [block({})], [appt({ start_time: '17:00', end_time: '17:30' })])).toEqual({ start: 540, end: 1080 });
  });
});
