import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton, FilterPills } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { WEEKDAY_LABELS } from '@/constants/domainConstants';
import { useEmrSettings } from '../useEmrSettings';
import type { EmrScheduleBlock } from '../types';

const SLOT_OPTIONS = [10, 15, 20, 30, 45, 60].map((m) => ({ key: String(m), label: `${m} min` }));
const WEEKDAY_OPTIONS = WEEKDAY_LABELS.map((label, i) => ({ key: String(i), label: label.slice(0, 3) }));

const fieldCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';

export interface ScheduleBlockModalProps {
  open: boolean;
  doctorId: string;
  /** Existing block to edit; omit to add a new one. */
  block?: EmrScheduleBlock | null;
  /** Weekday to preselect for a new block. */
  defaultWeekday?: number;
  onClose: () => void;
  onSaved: () => void;
}

export default function ScheduleBlockModal({ open, doctorId, block, defaultWeekday = 0, onClose, onSaved }: ScheduleBlockModalProps) {
  const [weekday, setWeekday] = useState('0');
  const [start, setStart] = useState('09:00');
  const [end, setEnd] = useState('13:00');
  const [slot, setSlot] = useState('15');
  const [busy, setBusy] = useState(false);
  const { settings } = useEmrSettings(open);
  const defaultSlot = settings?.default_slot_minutes || 15;

  useEffect(() => {
    if (!open) return;
    setWeekday(String(block ? block.weekday : defaultWeekday));
    setStart(block?.start_time || '09:00');
    setEnd(block?.end_time || '13:00');
    setSlot(String(block?.slot_minutes || defaultSlot));
  }, [open, block, defaultWeekday, defaultSlot]);

  const submit = async () => {
    setBusy(true);
    try {
      const body = { weekday: Number(weekday), start_time: start, end_time: end, slot_minutes: Number(slot) };
      if (block) await api.put(apiUrl.emrSchedule(block.id), body);
      else await api.post(apiUrl.emrSchedules(), { ...body, doctor_user_id: doctorId });
      toast.success(block ? 'Working hours updated' : 'Working hours added');
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{block ? 'Edit working hours' : 'Add working hours'}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div>
            <span className={labelCls}>Day</span>
            <FilterPills options={WEEKDAY_OPTIONS} active={weekday} onChange={setWeekday} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="block-start" className={labelCls}>From</label>
              <input id="block-start" type="time" value={start} onChange={(e) => setStart(e.target.value)}
                className={fieldCls} data-testid="block-start-input" />
            </div>
            <div>
              <label htmlFor="block-end" className={labelCls}>To</label>
              <input id="block-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)}
                className={fieldCls} data-testid="block-end-input" />
            </div>
          </div>
          <div>
            <span className={labelCls}>Appointment length</span>
            <FilterPills options={SLOT_OPTIONS} active={slot} onChange={setSlot} />
          </div>
        </div>
        <DialogFooter className="mt-6">
          <AppButton variant="secondary" onClick={onClose} disabled={busy}>Cancel</AppButton>
          <AppButton onClick={submit} loading={busy} disabled={!start || !end} data-testid="submit-block-btn">
            {block ? 'Update' : 'Add hours'}
          </AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
