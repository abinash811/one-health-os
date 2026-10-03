import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton, StatusBadge } from '@/components/shared';
import { APPOINTMENT_TYPE } from '@/constants/domainConstants';
import { formatDate } from '@/utils/dates';
import { to12h } from '../timeFormat';
import type { EmrAppointment } from '../types';
import FeeChip from './FeeChip';
import QueueActions, { type QueueActionsProps } from './QueueActions';

export interface AppointmentDetailDialogProps extends Omit<QueueActionsProps, 'appointment'> {
  appointment: EmrAppointment | null;
  onClose: () => void;
  onOpenPatient: (a: EmrAppointment) => void;
}

/** Click a visit on the calendar → who, when, fee, and the same next-step buttons as the queue. */
export default function AppointmentDetailDialog({ appointment: a, onClose, onOpenPatient, ...actions }: AppointmentDetailDialogProps) {
  const walkIn = a?.appointment_type === APPOINTMENT_TYPE.WALK_IN;
  const row = (label: string, value: React.ReactNode) => (
    <div className="flex justify-between gap-4 py-2 border-b border-gray-100 last:border-0">
      <dt className="text-xs font-bold text-gray-500 uppercase tracking-wide">{label}</dt>
      <dd className="text-sm text-gray-900 text-right">{value}</dd>
    </div>
  );
  return (
    <Dialog open={!!a} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="appointment-detail">
        {a && (
          <>
            <DialogHeader><DialogTitle>{a.patient_name || 'Appointment'}</DialogTitle></DialogHeader>
            <dl>
              {row('Status', <StatusBadge status={a.status} />)}
              {row('When', `${formatDate(a.appointment_date)} · ${walkIn ? `Walk-in, token #${a.token_number}` : to12h(a.start_time)}`)}
              {row('Doctor', a.doctor_name || '—')}
              {row('Reason', a.reason || '—')}
              {row('Fee', <FeeChip fee={a.fee} />)}
            </dl>
            <div className="flex items-center justify-between gap-2 pt-2">
              <AppButton variant="ghost" size="sm" onClick={() => onOpenPatient(a)} data-testid="open-patient-btn">Patient profile</AppButton>
              <QueueActions appointment={a} {...actions} />
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
