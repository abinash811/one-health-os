/**
 * EMR Doctor Schedules — each doctor's weekly working hours.
 * Route: /emr/schedules (docs/28_EMR_SCOPE.md). These blocks are what the
 * booking dialog turns into bookable slots.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { CalendarClock, Pencil, Plus, Trash2 } from 'lucide-react';
import {
  PageHeader, PageTabs, DataCard, AppButton, EmptyState, TableSkeleton, DeleteConfirmDialog,
} from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { WEEKDAY_LABELS } from '@/constants/domainConstants';
import { EMR_TABS, emrTabRoute } from '../emrTabs';
import { to12h } from '../timeFormat';
import DoctorSelect from '../components/DoctorSelect';
import ScheduleBlockModal from '../components/ScheduleBlockModal';
import type { EmrDoctor, EmrScheduleBlock } from '../types';

export default function DoctorSchedules() {
  const navigate = useNavigate();
  const [doctors, setDoctors] = useState<EmrDoctor[]>([]);
  const [doctorId, setDoctorId] = useState('');
  const [blocks, setBlocks] = useState<EmrScheduleBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<EmrScheduleBlock | null>(null);
  const [weekday, setWeekday] = useState(0);
  const [deleting, setDeleting] = useState<EmrScheduleBlock | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    api.get(apiUrl.emrDoctors())
      .then((res: { data: EmrDoctor[] }) => {
        setDoctors(res.data || []);
        if (res.data?.length) setDoctorId((cur) => cur || res.data[0].id);
        else setLoading(false);
      })
      .catch((err: Error) => { toast.error(err.message); setLoading(false); });
  }, []);

  const fetchBlocks = useCallback(async () => {
    if (!doctorId) return;
    setLoading(true);
    try {
      const res = await api.get(apiUrl.emrSchedules({ doctor_user_id: doctorId }));
      setBlocks(res.data || []);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => { fetchBlocks(); }, [fetchBlocks]);

  const openModal = (block: EmrScheduleBlock | null, day = 0) => {
    setEditing(block); setWeekday(day); setModalOpen(true);
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(apiUrl.emrSchedule(deleting.id));
      toast.success('Working hours removed');
      setDeleting(null);
      fetchBlocks();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-schedules-page">
      <PageHeader
        title="Clinic"
        actions={(
          <AppButton icon={<Plus className="w-4 h-4" />} disabled={!doctorId} onClick={() => openModal(null)}
            data-testid="add-hours-btn">
            Add Working Hours
          </AppButton>
        )}
      />
      <PageTabs tabs={EMR_TABS} activeTab="schedules" onChange={(k) => navigate(emrTabRoute(k))} />

      <div className="mb-4">
        <DoctorSelect doctors={doctors} value={doctorId} onChange={setDoctorId} testId="schedule-doctor-select" />
      </div>

      {doctors.length === 0 && !loading ? (
        <DataCard>
          <EmptyState icon={CalendarClock} title="No doctors yet"
            description="Add a team member with the Doctor role in Team, then set their working hours here." />
        </DataCard>
      ) : (
        <DataCard noPadding>
          {loading ? <TableSkeleton rows={7} columns={3} /> : (
            <ul className="divide-y" data-testid="schedule-week">
              {WEEKDAY_LABELS.map((dayLabel, day) => {
                const dayBlocks = blocks.filter((b) => b.weekday === day);
                return (
                  <li key={dayLabel} className="flex items-center gap-4 px-4 py-3" data-testid={`schedule-day-${day}`}>
                    <span className="w-28 text-sm font-medium text-gray-900">{dayLabel}</span>
                    <div className="flex-1 flex flex-wrap items-center gap-2">
                      {dayBlocks.length === 0 && <span className="text-sm text-gray-400">Not working</span>}
                      {dayBlocks.map((b) => (
                        <span key={b.id} className="inline-flex items-center gap-1 pl-3 pr-1 py-1 rounded-full bg-brand-subtle text-brand text-sm"
                          data-testid={`block-${b.id}`}>
                          {to12h(b.start_time)} – {to12h(b.end_time)} · {b.slot_minutes} min
                          <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-3.5 h-3.5" />}
                            aria-label={`Edit ${dayLabel} hours`} onClick={() => openModal(b, day)} />
                          <AppButton variant="ghost" size="sm" iconOnly icon={<Trash2 className="w-3.5 h-3.5" />}
                            aria-label={`Remove ${dayLabel} hours`} onClick={() => setDeleting(b)}
                            data-testid={`delete-block-${b.id}`} />
                        </span>
                      ))}
                    </div>
                    <AppButton variant="ghost" size="sm" onClick={() => openModal(null, day)}>+ Add</AppButton>
                  </li>
                );
              })}
            </ul>
          )}
        </DataCard>
      )}

      <ScheduleBlockModal open={modalOpen} doctorId={doctorId} block={editing} defaultWeekday={weekday}
        onClose={() => setModalOpen(false)} onSaved={fetchBlocks} />
      <DeleteConfirmDialog open={!!deleting} itemName="these working hours" isLoading={deleteBusy}
        onClose={() => setDeleting(null)} onConfirm={confirmDelete} />
    </div>
  );
}
