/**
 * EMR Settings — clinic profile, ID formats, patient-form layout and doctor
 * profiles. Route: /emr/settings. Everyone in the clinic can read; only admins
 * can save (the backend enforces it — the form is simply read-only for others).
 */
import React, { useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Save } from 'lucide-react';
import { PageHeader, PageTabs, AppButton, DataCard, ErrorState, TableSkeleton } from '@/components/shared';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { USER_ROLE } from '@/constants/domainConstants';
import { EMR_TABS, emrTabRoute } from '../emrTabs';
import ClinicProfileCard from '../components/ClinicProfileCard';
import IdFormatsCard from '../components/IdFormatsCard';
import PatientFormCard from '../components/PatientFormCard';
import DoctorsCard from '../components/DoctorsCard';
import DoctorProfileModal from '../components/DoctorProfileModal';
import { SettingsDraft, toDraft, toPayload } from '../settingsDraft';
import type { EmrDoctorProfile, EmrSettings } from '../types';

export default function EmrSettingsPage() {
  const navigate = useNavigate();
  const { user } = useContext(AuthContext) as unknown as { user: { role: string } | null };
  const canEdit = user?.role === USER_ROLE.ADMIN;
  const [settings, setSettings] = useState<EmrSettings | null>(null);
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [error, setError] = useState('');
  const [doctors, setDoctors] = useState<EmrDoctorProfile[]>([]);
  const [doctorsLoading, setDoctorsLoading] = useState(true);
  const [editing, setEditing] = useState<EmrDoctorProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api.get(apiUrl.emrSettings())
      .then((res: { data: EmrSettings }) => { setSettings(res.data); setDraft(toDraft(res.data)); })
      .catch((err: Error) => setError(err.message));
  }, [tick]);

  useEffect(() => {
    api.get(apiUrl.emrDoctorProfiles())
      .then((res: { data: EmrDoctorProfile[] }) => setDoctors(res.data || []))
      .catch((err: Error) => toast.error(err.message))
      .finally(() => setDoctorsLoading(false));
  }, [tick]);

  const patch = (p: Partial<SettingsDraft>) => setDraft((d) => (d ? { ...d, ...p } : d));

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const res = await api.put(apiUrl.emrSettings(), toPayload(draft));
      setSettings(res.data); setDraft(toDraft(res.data));
      toast.success('Settings saved');
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-settings-page">
      <PageHeader
        title="Clinic"
        actions={canEdit && (
          <AppButton icon={<Save className="w-4 h-4" />} loading={saving} disabled={!draft} onClick={save}
            data-testid="save-settings-btn">Save changes</AppButton>
        )}
      />
      <PageTabs tabs={EMR_TABS} activeTab="settings" onChange={(k) => navigate(emrTabRoute(k))} />

      {error ? (
        <DataCard><ErrorState message={error} onRetry={() => { setError(''); setTick((t) => t + 1); }} /></DataCard>
      ) : !draft || !settings ? (
        <DataCard noPadding><TableSkeleton rows={6} columns={3} /></DataCard>
      ) : (
        <div className="space-y-4 max-w-4xl">
          {!canEdit && (
            <p className="text-sm text-gray-600 bg-white border border-gray-200 rounded-lg px-4 py-3" data-testid="settings-readonly-note">
              You can view these settings. Only a clinic admin can change them.
            </p>
          )}
          <ClinicProfileCard draft={draft} fallback={settings.fallback} readOnly={!canEdit} onChange={patch} />
          <IdFormatsCard draft={draft} uhidNext={settings.uhid_next} readOnly={!canEdit} onChange={patch} />
          <PatientFormCard value={draft.patient_form} readOnly={!canEdit} onChange={(v) => patch({ patient_form: v })} />
          <DoctorsCard doctors={doctors} loading={doctorsLoading} readOnly={!canEdit} onEdit={setEditing} />
        </div>
      )}

      <DoctorProfileModal doctor={editing} onClose={() => setEditing(null)} onSaved={() => setTick((t) => t + 1)} />
    </div>
  );
}
