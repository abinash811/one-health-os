/**
 * "Doctors at this clinic" (Settings → Organisation → Clinics). The clinic-side view of the doctor↔clinic
 * mapping: tick a doctor to practise here (with this clinic's fee), untick to remove. Nothing is deleted —
 * an unticked doctor keeps their history and comes back if ticked again (docs/32_CLINICS_SCOPE.md P2c).
 */
import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Stethoscope } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AppButton, EmptyState, InlineLoader } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { toPaise, toRupees } from '@/utils/currency';
import type { Clinic } from './types';

interface ClinicDoctor {
  id: string;
  name: string;
  specialty: string | null;
  registration_no: string | null;
  is_external: boolean;
  mapped: boolean;
  consultation_fee_paise: number | null;
}

interface Props { clinic: Clinic | null; canEdit: boolean; onClose: () => void }

export default function ClinicDoctorsModal({ clinic, canEdit, onClose }: Props) {
  const [rows, setRows] = useState<ClinicDoctor[]>([]);
  const [fees, setFees] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!clinic) return;
    setLoading(true);
    try {
      const res = await api.get(apiUrl.clinicDoctors(clinic.id));
      const data: ClinicDoctor[] = res.data || [];
      setRows(data);
      setFees(Object.fromEntries(data.map((d) => [d.id, d.consultation_fee_paise ? String(toRupees(d.consultation_fee_paise)) : ''])));
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [clinic]);

  useEffect(() => { if (clinic) load(); }, [clinic, load]);

  const feeBad = (id: string) => fees[id]?.trim() !== '' && !(Number(fees[id]) >= 0);

  const save = async (d: ClinicDoctor, run: () => Promise<unknown>, done: string) => {
    setBusyId(d.id);
    try {
      await run();
      toast.success(done);
      await load();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const feeBody = (d: ClinicDoctor) => ({
    consultation_fee_paise: fees[d.id].trim() === '' ? null : toPaise(Number(fees[d.id])),
  });

  const toggle = (d: ClinicDoctor) => d.mapped
    ? save(d, () => api.delete(apiUrl.clinicDoctor(clinic!.id, d.id)), `${d.name} removed from ${clinic!.name}`)
    : save(d, () => api.put(apiUrl.clinicDoctor(clinic!.id, d.id), feeBody(d)), `${d.name} now practises at ${clinic!.name}`);

  return (
    <Dialog open={!!clinic} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Doctors at {clinic?.name}</DialogTitle>
          <DialogDescription>Tick the doctors who practise here. The fee is added to the patient's bill at check-in.</DialogDescription>
        </DialogHeader>
        {loading ? (
          <div className="py-8 flex justify-center"><InlineLoader text="Loading doctors..." /></div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Stethoscope} title="No doctors yet" description="Add doctors under Settings → Organisation → Doctors first." />
        ) : (
          <ul className="space-y-2 mt-2 max-h-[50vh] overflow-auto" data-testid="clinic-doctors-list">
            {rows.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-3 py-2 rounded-lg border border-gray-200" data-testid={`clinic-doctor-${d.id}`}>
                <input type="checkbox" id={`cd-${d.id}`} checked={d.mapped} disabled={!canEdit || busyId === d.id || feeBad(d.id)}
                  onChange={() => toggle(d)} className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid={`clinic-doctor-on-${d.id}`} />
                <label htmlFor={`cd-${d.id}`} className="flex-1 min-w-0">
                  <span className="block text-sm font-medium text-gray-900 truncate">
                    {d.name}{d.is_external && <span className="ml-2 text-xs font-normal text-gray-500">External</span>}
                  </span>
                  <span className="block text-xs text-gray-500 truncate">{d.specialty || d.registration_no || '—'}</span>
                </label>
                <label htmlFor={`cdfee-${d.id}`} className="text-xs text-gray-500">Fee ₹</label>
                <input id={`cdfee-${d.id}`} type="number" min="0" step="1" value={fees[d.id] ?? ''} disabled={!canEdit || busyId === d.id}
                  onChange={(e) => setFees((s) => ({ ...s, [d.id]: e.target.value }))} placeholder="no fee" aria-invalid={feeBad(d.id)}
                  className="w-24 px-2 py-1 border border-gray-200 rounded-lg text-sm disabled:bg-gray-50" data-testid={`clinic-doctor-fee-${d.id}`} />
                {d.mapped && canEdit && (
                  <AppButton size="sm" variant="secondary" disabled={busyId === d.id || feeBad(d.id)} data-testid={`clinic-doctor-save-${d.id}`}
                    onClick={() => save(d, () => api.put(apiUrl.clinicDoctor(clinic!.id, d.id), feeBody(d)), 'Fee saved')}>
                    Save
                  </AppButton>
                )}
              </li>
            ))}
          </ul>
        )}
        <DialogFooter className="mt-4"><AppButton variant="secondary" onClick={onClose}>Close</AppButton></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
