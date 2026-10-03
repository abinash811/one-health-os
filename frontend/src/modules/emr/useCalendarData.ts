import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import type { EmrAppointment, EmrDoctor, EmrScheduleBlock } from './types';

const REFRESH_MS = 30_000;

/** Doctors + working hours once; the visit list for [from, to] on a 30s refresh so the front desk sees check-ins. */
export function useCalendarData(from: string, to: string, doctorId?: string) {
  const [doctors, setDoctors] = useState<EmrDoctor[]>([]);
  const [schedules, setSchedules] = useState<EmrScheduleBlock[]>([]);
  const [appointments, setAppointments] = useState<EmrAppointment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(apiUrl.emrDoctors()).then((r: { data: EmrDoctor[] }) => setDoctors(r.data || []))
      .catch((err: Error) => toast.error(err.message));
    api.get(apiUrl.emrSchedules()).then((r: { data: EmrScheduleBlock[] }) => setSchedules(r.data || []))
      .catch((err: Error) => toast.error(err.message));
  }, []);

  const reload = useCallback(async (showSkeleton: boolean) => {
    if (showSkeleton) setLoading(true);
    try {
      const res = await api.get(apiUrl.emrAppointments({ date_from: from, date_to: to, doctor_id: doctorId }));
      setAppointments(res.data || []);
    } catch (err) {
      if (showSkeleton) toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [from, to, doctorId]);

  useEffect(() => {
    reload(true);
    const timer = setInterval(() => reload(false), REFRESH_MS);
    return () => clearInterval(timer);
  }, [reload]);

  return { doctors, schedules, appointments, loading, reload };
}
