/**
 * EmrClinicGate — wraps every EMR and patient-billing page. Those pages work on one clinic at a time, so
 * with no clinic active we show a plain next step instead of letting each page fail with an error:
 *   - has clinics, none active  → pick one right here
 *   - has none, can add clinics → link to Settings → Organisation → Clinics
 *   - has none, cannot          → ask an administrator for access
 */
import React from 'react';
import { Link, Outlet } from 'react-router-dom';
import { Stethoscope } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import AppButton from '@/components/shared/AppButton';
import { PageSkeleton } from '@/components/shared';
import { usePlaces } from '@/components/PlaceSwitcher';
import { canSeeClinics, settingsPath, HubUser } from '@/pages/SettingsHub/sections';

export default function EmrClinicGate({ user }: { user: HubUser }) {
  const places = usePlaces();
  const [switching, setSwitching] = React.useState(false);
  // Outside the app shell there is no place data to judge by — let the page render.
  if (!places) return <Outlet />;
  if (places.loading) return <PageSkeleton />;
  const { clinics } = places;
  if (clinics.some((c) => c.is_active)) return <Outlet />;

  const pick = async (clinicId: string) => {
    setSwitching(true);
    try {
      await api.post(apiUrl.switchClinic(), { clinic_id: clinicId });
      window.location.reload();
    } catch (error) {
      toast.error((error as Error).message);
      setSwitching(false);
    }
  };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-clinic-gate">
      <div className="max-w-md mx-auto mt-24 bg-white rounded-xl border border-gray-200 p-8 text-center">
        <Stethoscope className="w-8 h-8 text-brand mx-auto mb-3" strokeWidth={1.5} />
        {clinics.length > 0 ? (
          <>
            <h2 className="text-lg font-semibold text-gray-900">Choose a clinic to continue</h2>
            <p className="text-sm text-gray-600 mt-1 mb-4">Appointments, patients and patient bills belong to one clinic at a time.</p>
            <div className="flex flex-col gap-2">
              {clinics.map((c) => (
                <AppButton key={c.clinic_id} variant="secondary" disabled={switching} onClick={() => pick(c.clinic_id)}
                  data-testid={`gate-clinic-${c.clinic_id}`}>{c.clinic_name}</AppButton>
              ))}
            </div>
          </>
        ) : canSeeClinics(user) ? (
          <>
            <h2 className="text-lg font-semibold text-gray-900">Add your first clinic</h2>
            <p className="text-sm text-gray-600 mt-1 mb-4">EMR needs a clinic to work in. It takes a minute.</p>
            <Link to={settingsPath('organisation', 'clinics')} data-testid="gate-add-clinic">
              <AppButton>Add a clinic</AppButton>
            </Link>
          </>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-gray-900">No clinic access yet</h2>
            <p className="text-sm text-gray-600 mt-1">Ask an administrator to give you access to a clinic (Users → Clinic access).</p>
          </>
        )}
      </div>
    </div>
  );
}
