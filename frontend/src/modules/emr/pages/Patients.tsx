/**
 * EMR Patients — the clinic's own patient register.
 * Route: /emr/patients (docs/28_EMR_SCOPE.md). Independent of the pharmacy
 * Customers page by design; each row shows where the record was added.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Pencil, Trash2, UserPlus, Users } from 'lucide-react';
import {
  PageHeader, PageTabs, DataCard, TableSkeleton, PaginationBar, AppButton,
  EmptyState, SearchInput, DeleteConfirmDialog,
} from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import usePagination from '@/hooks/usePagination';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import { ROUTES } from '@/constants/routes';
import { EMR_TABS, emrTabRoute } from '../emrTabs';
import PatientFormModal from '../components/PatientFormModal';
import type { EmrPatient } from '../types';

const SOURCE_LABELS: Record<string, string> = { emr: 'Added in EMR', pharmacy: 'Added in pharmacy' };

const TH = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';

export default function Patients() {
  const navigate = useNavigate();
  const [patients, setPatients] = useState<EmrPatient[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EmrPatient | null>(null);
  const [deleting, setDeleting] = useState<EmrPatient | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const pager = usePagination({ pageSize: 20 });
  const { page, queryParams, setFromResponse, resetPage } = pager;

  const applySearch = useDebouncedCallback((value: string) => { setQuery(value); resetPage(); }, 300);

  const fetchPatients = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(apiUrl.emrPatients({ ...queryParams, search: query || undefined }));
      setPatients(res.data.data || []);
      setFromResponse(res.data.pagination);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, query]);

  useEffect(() => { fetchPatients(); }, [fetchPatients]);

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(apiUrl.emrPatient(deleting.id));
      toast.success('Patient deleted');
      setDeleting(null);
      fetchPatients();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setDeleteBusy(false);
    }
  };

  const openForm = (p: EmrPatient | null) => { setEditing(p); setFormOpen(true); };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-patients-page">
      <PageHeader
        title="Clinic"
        actions={(
          <AppButton icon={<UserPlus className="w-4 h-4" />} onClick={() => openForm(null)} data-testid="add-patient-btn">
            Register Patient
          </AppButton>
        )}
      />
      <PageTabs tabs={EMR_TABS} activeTab="patients" onChange={(k) => navigate(emrTabRoute(k))} />

      <div className="mb-4 max-w-sm">
        <SearchInput value={search} onChange={(v) => { setSearch(v); applySearch(v); }}
          placeholder="Search by name or mobile" />
      </div>

      <DataCard noPadding>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="emr-patients-table">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className={TH}>Patient</th>
                <th className={TH}>Mobile</th>
                <th className={TH}>Age / Gender</th>
                <th className={TH}>Allergies</th>
                <th className={TH}>Source</th>
                <th className={`${TH} text-right`}>Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr><td colSpan={6} className="p-0"><TableSkeleton rows={8} columns={6} /></td></tr>
              ) : patients.length === 0 ? (
                <tr><td colSpan={6}>
                  <EmptyState
                    icon={Users}
                    title={query ? 'No patients match your search' : 'No patients yet'}
                    description={query ? 'Try a different name or mobile number.' : 'Register your first patient to start booking appointments.'}
                    action={!query && <AppButton onClick={() => openForm(null)}>Register Patient</AppButton>}
                  />
                </td></tr>
              ) : patients.map((p) => (
                <tr key={p.id} className="hover:bg-brand-tint transition-colors" data-testid={`patient-row-${p.id}`}>
                  <td className="px-4 py-3">
                    <AppButton variant="chip" onClick={() => navigate(ROUTES.EMR.PATIENT(p.id))}
                      data-testid={`open-patient-${p.id}`}>{p.name}</AppButton>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{p.phone || '—'}</td>
                  <td className="px-4 py-3 text-gray-700">
                    {[p.age != null ? `${p.age} y` : null, p.gender].filter(Boolean).join(' · ') || '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-700 max-w-[200px] truncate" title={p.allergies || undefined}>{p.allergies || '—'}</td>
                  <td className="px-4 py-3 text-xs text-gray-500">{SOURCE_LABELS[p.source] || p.source}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-4 h-4" />}
                      aria-label={`Edit ${p.name}`} onClick={() => openForm(p)} data-testid={`edit-patient-${p.id}`} />
                    <AppButton variant="ghost" size="sm" iconOnly icon={<Trash2 className="w-4 h-4" />}
                      aria-label={`Delete ${p.name}`} onClick={() => setDeleting(p)} data-testid={`delete-patient-${p.id}`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <PaginationBar {...pager} />
      </DataCard>

      <PatientFormModal open={formOpen} patient={editing} onClose={() => setFormOpen(false)} onSaved={fetchPatients} />
      <DeleteConfirmDialog open={!!deleting} itemName={deleting?.name} isLoading={deleteBusy}
        onClose={() => setDeleting(null)} onConfirm={confirmDelete} />
    </div>
  );
}
