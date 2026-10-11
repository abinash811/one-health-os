/**
 * SettingsPlaceBar — says, at the top of every settings panel, WHICH place the settings on screen belong to.
 * Pharmacy settings belong to one pharmacy, EMR settings to one clinic, Organisation settings to the whole
 * workspace. Without this the only clue was the small selector in the page header.
 */
import React, { useContext } from 'react';
import { AlertTriangle, Building2, Landmark, Stethoscope } from 'lucide-react';
import { AuthContext } from '@/App';
import { usePlaces } from '@/components/PlaceSwitcher';

export default function SettingsPlaceBar({ moduleKey }: { moduleKey: string }) {
  const places = usePlaces();
  const { user } = useContext(AuthContext) as unknown as { user: { workspace?: { name?: string } | null } | null };

  let icon = <Landmark className="w-4 h-4" />;
  let body: React.ReactNode = null;
  let warn = false;

  if (moduleKey === 'organisation') {
    const org = user?.workspace?.name;
    body = <>These settings apply to your whole organisation{org ? <> — <strong>{org}</strong></> : null}.</>;
  } else if (moduleKey === 'pharmacy' || moduleKey === 'emr') {
    if (!places) return null;
    const clinic = moduleKey === 'emr';
    const active = clinic
      ? places.clinics.find((c) => c.is_active)?.clinic_name
      : places.stores.find((s) => s.is_active)?.pharmacy_name;
    icon = clinic ? <Stethoscope className="w-4 h-4" /> : <Building2 className="w-4 h-4" />;
    if (places.loading) return null;
    if (active) {
      body = (<>
        Editing settings for <strong data-testid="settings-place-name">{active}</strong> — changes apply to this {clinic ? 'clinic' : 'pharmacy'} only.
        {' '}To edit another, switch {clinic ? 'clinic' : 'pharmacy'} from the selector at the top.
      </>);
    } else {
      warn = true;
      icon = <AlertTriangle className="w-4 h-4" />;
      body = clinic
        ? 'No clinic selected. Pick one from the selector at the top, or add a clinic under Organisation → Clinics.'
        : 'No pharmacy selected. Pick one from the selector at the top.';
    }
  } else {
    return null;
  }

  return (
    <div role="status" data-testid="settings-place-bar"
      className={`flex items-start gap-2.5 rounded-lg border px-4 py-2.5 mb-4 text-sm ${
        warn ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-brand/20 bg-brand-subtle text-gray-800'}`}>
      <span className="mt-0.5 flex-shrink-0 text-brand">{icon}</span>
      <p>{body}</p>
    </div>
  );
}
