import React from 'react';
import { CheckCircle2, FileText, LogIn, Play, UserX, XCircle } from 'lucide-react';
import { AppButton, MoreMenu } from '@/components/shared';
import { APPOINTMENT_STATUS } from '@/constants/domainConstants';
import type { EmrAppointment } from '../types';

export interface QueueActionsProps {
  appointment: EmrAppointment;
  busy: boolean;
  onMove: (appointment: EmrAppointment, status: string) => void;
  onCancel: (appointment: EmrAppointment) => void;
  /** Opens the visit's prescription (consultation) screen. */
  onOpenRx: (appointment: EmrAppointment) => void;
}

/** The next-step button for a queue row, plus Cancel / No-show where they apply. */
export default function QueueActions({ appointment: a, busy, onMove, onCancel, onOpenRx }: QueueActionsProps) {
  const S = APPOINTMENT_STATUS;
  const primary: Record<string, { label: string; next: string; icon: React.ReactNode }> = {
    [S.BOOKED]:     { label: 'Check in',      next: S.CHECKED_IN, icon: <LogIn className="w-4 h-4" /> },
    [S.CHECKED_IN]: { label: 'Start consult', next: S.IN_CONSULT, icon: <Play className="w-4 h-4" /> },
    [S.IN_CONSULT]: { label: 'Complete',      next: S.COMPLETED,  icon: <CheckCircle2 className="w-4 h-4" /> },
  };
  const step = primary[a.status];
  const canOpenRx = a.status === S.IN_CONSULT || a.status === S.COMPLETED;
  const canCancel = a.status === S.BOOKED || a.status === S.CHECKED_IN;

  return (
    <div className="flex items-center justify-end gap-1">
      {canOpenRx && (
        <AppButton size="sm" variant={a.status === S.IN_CONSULT ? 'primary' : 'outline'} icon={<FileText className="w-4 h-4" />}
          onClick={() => onOpenRx(a)} data-testid={`queue-rx-${a.id}`}>
          {a.status === S.IN_CONSULT ? 'Write Rx' : 'View Rx'}
        </AppButton>
      )}
      {step && (
        <AppButton size="sm" variant="outline" icon={step.icon} loading={busy}
          onClick={() => onMove(a, step.next)} data-testid={`queue-next-${a.id}`}>
          {step.label}
        </AppButton>
      )}
      {canCancel && (
        <MoreMenu
          testId={`queue-more-${a.id}`}
          items={[
            a.status === S.BOOKED && {
              icon: <UserX className="w-4 h-4" />, label: 'Mark no-show', action: () => onMove(a, S.NO_SHOW),
            },
            {
              icon: <XCircle className="w-4 h-4" />, label: 'Cancel appointment', action: () => onCancel(a),
            },
          ]}
        />
      )}
    </div>
  );
}
