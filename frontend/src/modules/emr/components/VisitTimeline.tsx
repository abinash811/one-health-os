import React from 'react';
import { FileText, Printer } from 'lucide-react';
import { AppButton, StatusBadge } from '@/components/shared';
import { ROUTES } from '@/constants/routes';
import { APPOINTMENT_TYPE, PRESCRIPTION_STATUS } from '@/constants/domainConstants';
import { formatDate } from '@/utils/dates';
import { to12h } from '../timeFormat';
import type { EmrAppointment, EmrPrescription } from '../types';

export interface VisitTimelineProps {
  appointments: EmrAppointment[];
  /** The patient's prescriptions; matched to visits by appointment id. */
  prescriptions: EmrPrescription[];
  onOpen: (path: string) => void;
}

/** Newest-first list of every visit, each with its prescription (if any) inline. */
export default function VisitTimeline({ appointments, prescriptions, onOpen }: VisitTimelineProps) {
  const rxFor = (apptId: string) =>
    prescriptions.find((r) => r.appointment_id === apptId && r.status !== PRESCRIPTION_STATUS.CANCELLED);

  return (
    <ul className="divide-y" data-testid="visit-timeline">
      {appointments.map((a) => {
        const rx = rxFor(a.id);
        const when = a.appointment_type === APPOINTMENT_TYPE.WALK_IN ? 'Walk-in' : to12h(a.start_time);
        return (
          <li key={a.id} className="px-4 py-4" data-testid={`visit-${a.id}`}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-semibold text-gray-900">{formatDate(a.appointment_date)}</span>
              <span className="text-sm text-gray-500">{when} · {a.doctor_name || '—'}</span>
              <StatusBadge status={a.status} />
              {rx && <StatusBadge status={rx.status} />}
              <div className="ml-auto flex items-center gap-1">
                {rx && (
                  <>
                    <AppButton variant="outline" size="sm" icon={<FileText className="w-4 h-4" />}
                      onClick={() => onOpen(ROUTES.EMR.CONSULT(a.id))} data-testid={`visit-open-${a.id}`}>
                      {rx.status === PRESCRIPTION_STATUS.ISSUED ? 'View' : 'Continue'}
                    </AppButton>
                    {rx.status === PRESCRIPTION_STATUS.ISSUED && (
                      <AppButton variant="ghost" size="sm" iconOnly icon={<Printer className="w-4 h-4" />}
                        aria-label={`Print ${rx.rx_number}`} onClick={() => onOpen(ROUTES.EMR.RX_PRINT(rx.id))}
                        data-testid={`visit-print-${a.id}`} />
                    )}
                  </>
                )}
              </div>
            </div>
            {a.reason && <p className="text-sm text-gray-600 mt-1">Reason: {a.reason}</p>}
            {a.cancel_reason && <p className="text-sm text-red-600 mt-1">Cancelled: {a.cancel_reason}</p>}
            {rx && (
              <div className="mt-2 text-sm">
                <p className="text-gray-900"><span className="font-mono text-xs text-gray-500">{rx.rx_number}</span>
                  {rx.diagnosis ? ` · ${rx.diagnosis}` : ''}</p>
                {rx.items.length > 0 && (
                  <p className="text-gray-600">{rx.items.map((i) => i.medicine_name).join(', ')}</p>
                )}
                {rx.follow_up_date && <p className="text-xs text-gray-500">Follow-up: {formatDate(rx.follow_up_date)}</p>}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
