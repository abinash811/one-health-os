import React from 'react';
import { AppButton } from '@/components/shared';
import { APPOINTMENT_STATUS } from '@/constants/domainConstants';
import { STATUS_CARD } from '../calendarUtils';
import { to12h } from '../timeFormat';
import type { EmrAppointment } from '../types';

export interface CalendarEventCardProps {
  appointment: EmrAppointment;
  /** Pixel position inside the column; omit for a walk-in chip (flows inline instead). */
  top?: number;
  height?: number;
  onOpen: (a: EmrAppointment) => void;
  onDragStart?: (a: EmrAppointment) => void;
  onDragEnd?: () => void;
}

/** One visit on the grid. Only a still-booked visit can be dragged to a new slot (the API refuses the rest). */
export default function CalendarEventCard({ appointment: a, top, height, onOpen, onDragStart, onDragEnd }: CalendarEventCardProps) {
  const positioned = top !== undefined && height !== undefined;
  const canDrag = a.status === APPOINTMENT_STATUS.BOOKED && !!onDragStart;
  const name = a.patient_name || 'Patient';
  const label = positioned ? `${name}, ${to12h(a.start_time)}, ${a.status.replace('_', ' ')}` : `Token ${a.token_number}, ${name}`;
  const card = `rounded-md border text-left text-xs ${STATUS_CARD[a.status] || STATUS_CARD[APPOINTMENT_STATUS.BOOKED]}`;
  return (
    <AppButton variant="chip" aria-label={label} title={a.reason || undefined} data-testid={`cal-event-${a.id}`}
      draggable={canDrag} onClick={() => onOpen(a)}
      onDragStart={canDrag ? (e) => { e.dataTransfer.setData('text/plain', a.id); onDragStart?.(a); } : undefined}
      onDragEnd={onDragEnd}
      className={positioned
        ? `absolute left-1 right-1 z-10 flex-col items-start justify-start gap-0 overflow-hidden whitespace-normal px-2 py-1 hover:brightness-95 ${card} ${canDrag ? 'cursor-grab' : ''}`
        : `inline-flex px-2 py-1 ${card}`}
      style={positioned ? { top, height: Math.max(height - 2, 20) } : undefined}>
      {positioned ? (
        <>
          <span className="block w-full truncate font-semibold">{name}</span>
          {height >= 40 && (
            <span className="block w-full truncate font-normal opacity-80">{to12h(a.start_time)}{a.reason ? ` · ${a.reason}` : ''}</span>
          )}
        </>
      ) : <span className="truncate">#{a.token_number} {name}</span>}
    </AppButton>
  );
}
