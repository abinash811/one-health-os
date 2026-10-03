/**
 * Settings → Organisation → Doctors. Doctors are profiles owned by the hospital and mapped to the
 * clinics where they practise — separate from the logins in Team (docs/31_CORE_DOCTOR_SCOPE.md).
 * Anyone ticked for `doctors:view` can read; `doctors:edit` adds, edits and removes.
 */
import React, { useCallback, useContext, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Pencil, Plus, Stethoscope, Trash2 } from 'lucide-react';
import { AppButton, DataCard, DeleteConfirmDialog, EmptyState, ErrorState, StatusBadge, TableSkeleton } from '@/components/shared';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { formatCurrency, toRupees } from '@/utils/currency';
import { hasPermission } from '@/utils/clinicAccess';
import DoctorFormModal from './DoctorFormModal';
import type { ClinicOption, Doctor } from './types';

const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';

export default function DoctorsPanel() {
  const { user } = useContext(AuthContext) as unknown as { user: { role?: string; is_super_admin?: boolean; permissions?: string[] } | null };
  const canEdit = !!user && (user.role === 'admin' || !!user.is_super_admin || hasPermission(user.permissions, 'doctors:edit'));
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [clinics, setClinics] = useState<ClinicOption[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<Doctor | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [removing, setRemoving] = useState<Doctor | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(apiUrl.practitioners({ include_inactive: showInactive ? true : undefined }));
      setDoctors(res.data || []);
      setError('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get(apiUrl.myStores())
      .then((res: { data: { pharmacy_id: string; pharmacy_name: string; is_active: boolean }[] }) =>
        setClinics((res.data || []).map((s) => ({ pharmacy_id: s.pharmacy_id, pharmacy_name: s.pharmacy_name, is_current: s.is_active }))))
      .catch((err: Error) => toast.error(err.message));
  }, []);

  const open = (d: Doctor | null) => { setEditing(d); setFormOpen(true); };

  const confirmRemove = async () => {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await api.delete(apiUrl.practitioner(removing.id));
      toast.success(`${removing.name} removed`);
      setRemoving(null);
      load();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setRemoveBusy(false);
    }
  };

  const fees = (d: Doctor) => d.clinics.map((c) => (
    <span key={c.pharmacy_id} className="inline-flex items-center rounded-full bg-brand-subtle text-brand text-xs px-2 py-0.5 mr-1 mb-1"
      title={c.consultation_fee_paise ? `Fee ${formatCurrency(toRupees(c.consultation_fee_paise))}` : 'No fee'}>
      {c.pharmacy_name}{c.consultation_fee_paise ? ` · ${formatCurrency(toRupees(c.consultation_fee_paise))}` : ''}
    </span>
  ));

  return (
    <div className="space-y-4" data-testid="doctors-panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Doctors</h2>
          <p className="text-sm text-gray-500">Profiles owned by your hospital, mapped to the clinics where they practise. Logins stay in Team.</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer whitespace-nowrap" htmlFor="show-inactive-doctors">
            <input id="show-inactive-doctors" type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid="show-inactive-doctors" />
            Show inactive
          </label>
          {canEdit && (
            <AppButton icon={<Plus className="w-4 h-4" />} onClick={() => open(null)} data-testid="add-doctor-btn">Add doctor</AppButton>
          )}
        </div>
      </div>
      {!canEdit && (
        <p className="text-sm text-gray-600 bg-white border border-gray-200 rounded-lg px-4 py-3" data-testid="doctors-readonly-note">
          You can view doctors. Only people ticked for “Create / Edit Doctors” can change them.
        </p>
      )}

      {error ? (
        <DataCard><ErrorState message={error} onRetry={load} /></DataCard>
      ) : (
        <DataCard noPadding>
          {loading ? <TableSkeleton rows={5} columns={5} /> : doctors.length === 0 ? (
            <EmptyState icon={Stethoscope} title="No doctors yet"
              description="Add a doctor to book appointments, set working hours and print prescriptions."
              action={canEdit ? <AppButton onClick={() => open(null)}>Add doctor</AppButton> : undefined} />
          ) : (
            <table className="w-full text-sm" data-testid="doctors-table">
              <thead className="bg-gray-50 border-b">
                <tr>{['Doctor', 'Registration no.', 'Works at', 'Login', 'Status', ''].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y">
                {doctors.map((d) => (
                  <tr key={d.id} className="hover:bg-brand-tint transition-colors" data-testid={`doctor-row-${d.id}`}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{d.name}{d.is_external && <span className="ml-2 text-xs font-normal text-gray-500">External</span>}</p>
                      <p className="text-xs text-gray-500">{[d.specialty, d.qualification].filter(Boolean).join(' · ') || '—'}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{d.registration_no || '—'}</td>
                    <td className="px-4 py-3 max-w-[260px]">{d.clinics.length ? fees(d) : <span className="text-gray-400">No clinic</span>}</td>
                    <td className="px-4 py-3 text-gray-700">{d.user_email || <span className="text-gray-400">No login</span>}</td>
                    <td className="px-4 py-3"><StatusBadge status={d.is_active ? 'active' : 'inactive'} /></td>
                    <td className="px-4 py-3">
                      {canEdit && (
                        <div className="flex justify-end gap-1">
                          <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-4 h-4" />}
                            aria-label={`Edit ${d.name}`} onClick={() => open(d)} data-testid={`edit-doctor-${d.id}`} />
                          <AppButton variant="ghost" size="sm" iconOnly icon={<Trash2 className="w-4 h-4" />}
                            aria-label={`Remove ${d.name}`} onClick={() => setRemoving(d)} data-testid={`remove-doctor-${d.id}`} />
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </DataCard>
      )}

      <DoctorFormModal open={formOpen} doctor={editing} clinics={clinics} onClose={() => setFormOpen(false)} onSaved={load} />
      <DeleteConfirmDialog open={!!removing} itemName={removing?.name || 'this doctor'} isLoading={removeBusy}
        onClose={() => setRemoving(null)} onConfirm={confirmRemove} />
    </div>
  );
}
