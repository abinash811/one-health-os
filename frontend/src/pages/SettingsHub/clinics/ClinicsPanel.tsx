/**
 * Settings → Organisation → Clinics. Clinics are EMR places owned by the hospital — separate from
 * pharmacies (docs/32_CLINICS_SCOPE.md). Create / edit / deactivate follow the role's clinics ticks.
 * A clinic is deactivated (and can be brought back), never deleted.
 */
import React, { useCallback, useContext, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Building2, Pencil, Plus, Power } from 'lucide-react';
import { AppButton, DataCard, EmptyState, ErrorState, StatusBadge, TableSkeleton } from '@/components/shared';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { hasPermission } from '@/utils/clinicAccess';
import ClinicFormModal from './ClinicFormModal';
import type { Clinic } from './types';

const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';

export default function ClinicsPanel() {
  const { user } = useContext(AuthContext) as unknown as { user: { role?: string; is_super_admin?: boolean; permissions?: string[] } | null };
  const admin = !!user && (user.role === 'admin' || !!user.is_super_admin);
  const canCreate = admin || (!!user && hasPermission(user.permissions, 'clinics:create'));
  const canEdit = admin || (!!user && hasPermission(user.permissions, 'clinics:edit'));
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<Clinic | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(apiUrl.clinics({ include_inactive: showInactive ? true : undefined }));
      setClinics(res.data || []);
      setError('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => { load(); }, [load]);

  const open = (c: Clinic | null) => { setEditing(c); setFormOpen(true); };

  const toggleActive = async (c: Clinic) => {
    try {
      await api.put(apiUrl.clinic(c.id), { is_active: !c.is_active });
      toast.success(c.is_active ? `${c.name} deactivated` : `${c.name} is active again`);
      load();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div className="space-y-4" data-testid="clinics-panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Clinics</h2>
          <p className="text-sm text-gray-500">Places where patients are seen (EMR). Pharmacies are managed separately.</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer whitespace-nowrap" htmlFor="show-inactive-clinics">
            <input id="show-inactive-clinics" type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid="show-inactive-clinics" />
            Show inactive
          </label>
          {canCreate && (
            <AppButton icon={<Plus className="w-4 h-4" />} onClick={() => open(null)} data-testid="add-clinic-btn">Add clinic</AppButton>
          )}
        </div>
      </div>
      {!canEdit && !canCreate && (
        <p className="text-sm text-gray-600 bg-white border border-gray-200 rounded-lg px-4 py-3" data-testid="clinics-readonly-note">
          You can view clinics. Only people ticked for “Create Clinics” or “Edit / Deactivate Clinics” can change them.
        </p>
      )}

      {error ? (
        <DataCard><ErrorState message={error} onRetry={load} /></DataCard>
      ) : (
        <DataCard noPadding>
          {loading ? <TableSkeleton rows={4} columns={5} /> : clinics.length === 0 ? (
            <EmptyState icon={Building2} title="No clinics yet"
              description="Add a clinic to start seeing patients, booking appointments and mapping doctors."
              action={canCreate ? <AppButton onClick={() => open(null)}>Add clinic</AppButton> : undefined} />
          ) : (
            <table className="w-full text-sm" data-testid="clinics-table">
              <thead className="bg-gray-50 border-b">
                <tr>{['Clinic', 'City', 'Phone', 'Status', ''].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y">
                {clinics.map((c) => (
                  <tr key={c.id} className="hover:bg-brand-tint transition-colors" data-testid={`clinic-row-${c.id}`}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{c.name}</p>
                      {c.registration_no && <p className="text-xs text-gray-500">Reg. {c.registration_no}</p>}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{c.city || '—'}</td>
                    <td className="px-4 py-3 text-gray-700">{c.phone || '—'}</td>
                    <td className="px-4 py-3"><StatusBadge status={c.is_active ? 'active' : 'inactive'} /></td>
                    <td className="px-4 py-3">
                      {canEdit && (
                        <div className="flex justify-end gap-1">
                          <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-4 h-4" />}
                            aria-label={`Edit ${c.name}`} onClick={() => open(c)} data-testid={`edit-clinic-${c.id}`} />
                          <AppButton variant="ghost" size="sm" iconOnly icon={<Power className="w-4 h-4" />}
                            aria-label={c.is_active ? `Deactivate ${c.name}` : `Reactivate ${c.name}`}
                            onClick={() => toggleActive(c)} data-testid={`toggle-clinic-${c.id}`} />
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

      <ClinicFormModal open={formOpen} clinic={editing} onClose={() => setFormOpen(false)} onSaved={load} />
    </div>
  );
}
