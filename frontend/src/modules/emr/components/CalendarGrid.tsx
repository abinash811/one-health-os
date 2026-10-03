import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { AppButton } from '@/components/shared';
import { APPOINTMENT_TYPE } from '@/constants/domainConstants';
import { PX_PER_MIN, slotsFor, toHHMM, toMinutes, workingRanges, type CalColumn, type Slot } from '../calendarUtils';
import { to12h } from '../timeFormat';
import type { EmrAppointment, EmrScheduleBlock } from '../types';
import CalendarEventCard from './CalendarEventCard';

export interface CalendarGridProps {
  columns: CalColumn[];
  schedules: EmrScheduleBlock[];
  /** Live visits only (cancelled / no-show free their slot, so they are not drawn). */
  appointments: EmrAppointment[];
  range: Slot;
  todayISO: string;
  nowMin: number;
  onSlotClick: (col: CalColumn, slot: Slot) => void;
  onOpen: (a: EmrAppointment) => void;
  onMove: (a: EmrAppointment, col: CalColumn, slot: Slot) => void;
}

const HEADER_H = 'h-12';
const WALKIN_H = 'h-10';

/** The time grid: a sticky time gutter, then one column per doctor (day view) or per weekday (week view). */
export default function CalendarGrid({ columns, schedules, appointments, range, todayISO, nowMin, onSlotClick, onOpen, onMove }: CalendarGridProps) {
  const [dragging, setDragging] = useState<EmrAppointment | null>(null);
  const px = (min: number) => (min - range.start) * PX_PER_MIN;
  const hours: number[] = [];
  for (let m = range.start; m < range.end; m += 60) hours.push(m);
  const hasWalkIns = appointments.some((a) => a.appointment_type === APPOINTMENT_TYPE.WALK_IN);
  const forColumn = (c: CalColumn) => appointments.filter((a) => a.doctor_user_id === c.doctorId && a.appointment_date === c.date);

  return (
    <div className="overflow-auto border border-gray-200 rounded-xl bg-white" style={{ maxHeight: 'calc(100vh - 280px)' }} data-testid="calendar-grid">
      <div className="flex min-w-max">
        <div className="sticky left-0 z-30 w-16 shrink-0 bg-white border-r border-gray-200">
          <div className={`${HEADER_H} sticky top-0 z-30 bg-white border-b border-gray-200`} />
          {hasWalkIns && <div className={`${WALKIN_H} flex items-center justify-end pr-2 text-[11px] text-gray-500 border-b border-gray-200`}>Walk-ins</div>}
          <div className="relative" style={{ height: px(range.end) }}>
            {hours.map((m) => (
              <span key={m} className={`absolute right-2 text-[11px] text-gray-500 whitespace-nowrap ${m === range.start ? 'mt-1' : '-translate-y-1/2'}`} style={{ top: px(m) }}>
                {to12h(toHHMM(m))}
              </span>
            ))}
          </div>
        </div>

        {columns.map((col) => {
          const colAppts = forColumn(col);
          const timed = colAppts.filter((a) => a.start_time);
          const taken = new Set(timed.map((a) => a.start_time));
          const isToday = col.date === todayISO;
          const canBook = col.date >= todayISO;
          return (
            <div key={col.key} className="flex-1 min-w-[170px] border-r border-gray-200 last:border-r-0" data-testid={`cal-col-${col.key}`}>
              <div className={`${HEADER_H} sticky top-0 z-20 bg-white border-b border-gray-200 px-3 flex flex-col justify-center`}>
                <span className="text-sm font-medium text-gray-900 truncate" title={col.title}>{col.title}</span>
                <span className={`text-xs truncate ${isToday ? 'text-brand font-medium' : 'text-gray-500'}`}>{isToday ? `Today · ${col.subtitle}` : col.subtitle}</span>
              </div>
              {hasWalkIns && (
                <div className={`${WALKIN_H} flex items-center gap-1 px-1 overflow-x-auto border-b border-gray-200`}>
                  {colAppts.filter((a) => !a.start_time).map((a) => <CalendarEventCard key={a.id} appointment={a} onOpen={onOpen} />)}
                </div>
              )}
              <div className="relative bg-gray-100" style={{ height: px(range.end) }}>
                {workingRanges(schedules, col.doctorId, col.date).map((r) => (
                  <div key={`${r.start}-${r.end}`} className="absolute inset-x-0 bg-white" style={{ top: px(r.start), height: (r.end - r.start) * PX_PER_MIN }} />
                ))}
                {hours.map((m) => <div key={m} className="absolute inset-x-0 border-t border-gray-200" style={{ top: px(m) }} />)}
                {slotsFor(schedules, col.doctorId, col.date).map((slot) => {
                  if (taken.has(toHHMM(slot.start))) return null;
                  const label = `Book ${col.title} ${col.date} at ${to12h(toHHMM(slot.start))}`;
                  return (
                    <AppButton key={slot.start} variant="chip" aria-label={label} title={label} disabled={!canBook}
                      data-testid={`cal-slot-${col.key}-${toHHMM(slot.start)}`} onClick={() => onSlotClick(col, slot)}
                      onDragOver={(e) => { if (dragging && canBook) e.preventDefault(); }}
                      onDrop={(e) => { e.preventDefault(); if (dragging) onMove(dragging, col, slot); setDragging(null); }}
                      className="group absolute inset-x-0 flex items-center justify-center rounded-none border-t border-dashed border-gray-100 text-transparent hover:bg-brand-tint hover:text-brand disabled:opacity-100 disabled:hover:bg-transparent"
                      style={{ top: px(slot.start), height: (slot.end - slot.start) * PX_PER_MIN }}>
                      {canBook && <Plus className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100" strokeWidth={1.5} />}
                    </AppButton>
                  );
                })}
                {timed.map((a) => {
                  const start = toMinutes(a.start_time!);
                  const end = a.end_time ? toMinutes(a.end_time) : start + 15;
                  return <CalendarEventCard key={a.id} appointment={a} top={px(start)} height={(end - start) * PX_PER_MIN}
                    onOpen={onOpen} onDragStart={setDragging} onDragEnd={() => setDragging(null)} />;
                })}
                {isToday && nowMin >= range.start && nowMin <= range.end && (
                  <div className="absolute inset-x-0 z-20 border-t-2 border-red-500 pointer-events-none" style={{ top: px(nowMin) }} data-testid="cal-now-line">
                    <span className="absolute -left-1 -top-[5px] w-2 h-2 rounded-full bg-red-500" />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
