/**
 * Clinic settings (Settings → EMR): clinic profile, ID formats, patient-form layout and doctor
 * profiles. Everyone in the clinic can read; only users ticked for `emr_settings:edit` can save
 * (the backend enforces it — the form is simply read-only for the rest). One draft is shared by
 * the form sections, so switching between them never loses unsaved edits.
 */
import React, { useContext, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Save } from 'lucide-react';
import { AppButton, DataCard, ErrorState, TableSkeleton } from '@/components/shared';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { hasPermission } from '@/utils/clinicAccess';
import ClinicProfileCard from './ClinicProfileCard';
import IdFormatsCard from './IdFormatsCard';
import PatientFormCard from './PatientFormCard';
import DoctorsCard from './DoctorsCard';
import DoctorProfileModal from './DoctorProfileModal';
import { SettingsDraft, toDraft, toPayload } from '../settingsDraft';
import type { EmrDoctorProfile, EmrSettings } from '../types';

export type EmrSettingsSection = 'clinic-profile' | 'id-formats' | 'patient-form' | 'doctors';

interface AuthUser { role: string; permissions?: string[]; is_super_admin?: boolean }

export default function EmrSettingsPanel({ section }: { section?: EmrSettingsSection }) {
  const { user } = useContext(AuthContext) as unknown as { user: AuthUser | null };
  const canEdit = user?.role === 'admin' || !!user?.is_super_admin
    || (!!user?.permissions && hasPermission(user.permissions, 'emr_settings:edit'));
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

  const show = (s: EmrSettingsSection) => !section || section === s;
  const showSave = canEdit && section !== 'doctors';

  if (error) return <DataCard><ErrorState message={error} onRetry={() => { setError(''); setTick((t) => t + 1); }} /></DataCard>;
  if (!draft || !settings) return <DataCard noPadding><TableSkeleton rows={6} columns={3} /></DataCard>;

  return (
    <div className="space-y-4 max-w-4xl" data-testid="emr-settings-page">
      {showSave && (
        <div className="flex justify-end">
          <AppButton icon={<Save className="w-4 h-4" />} loading={saving} onClick={save} data-testid="save-settings-btn">
            Save changes
          </AppButton>
        </div>
      )}
      {!canEdit && (
        <p className="text-sm text-gray-600 bg-white border border-gray-200 rounded-lg px-4 py-3" data-testid="settings-readonly-note">
          You can view these settings. Only a clinic admin can change them.
        </p>
      )}
      {show('clinic-profile') && <ClinicProfileCard draft={draft} fallback={settings.fallback} readOnly={!canEdit} onChange={patch} />}
      {show('id-formats') && <IdFormatsCard draft={draft} uhidNext={settings.uhid_next} readOnly={!canEdit} onChange={patch} />}
      {show('patient-form') && <PatientFormCard value={draft.patient_form} readOnly={!canEdit} onChange={(v) => patch({ patient_form: v })} />}
      {show('doctors') && <DoctorsCard doctors={doctors} loading={doctorsLoading} readOnly={!canEdit} onEdit={setEditing} />}
      <DoctorProfileModal doctor={editing} onClose={() => setEditing(null)} onSaved={() => setTick((t) => t + 1)} />
    </div>
  );
}
