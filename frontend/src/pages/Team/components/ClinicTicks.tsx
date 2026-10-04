/**
 * ClinicTicks — "Clinics they can open" tick-boxes on the Invite dialog (docs/32 P2d), so a new doctor or
 * receptionist can work straight away instead of needing a second step under Clinic access. The clinic you are
 * working at starts ticked when the chosen role is a clinic role. Renders nothing when there are no clinics
 * (or the viewer may not list them).
 */
import React, { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

interface Clinic { id: string; name: string }

const CLINIC_ROLE_PERMISSIONS = ['appointments:view', 'patients:view'];

interface Props {
  value: string[];
  onChange: (ids: string[]) => void;
  /** The role picked in the form — decides whether the working clinic is pre-ticked. */
  role: string;
  roles: { name: string; permissions?: string[] }[];
}

export default function ClinicTicks({ value, onChange, role, roles }: Props) {
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    api.get(apiUrl.clinics()).then((r: { data: Clinic[] }) => setClinics(r.data || [])).catch(() => setClinics([]));
    api.get(apiUrl.myClinics())
      .then((r: { data: { clinic_id: string; is_active: boolean }[] }) =>
        setActiveId((r.data || []).find((c) => c.is_active)?.clinic_id ?? null))
      .catch(() => setActiveId(null));
  }, []);

  // Picking a clinic role (doctor, receptionist…) ticks the clinic you are at; picking another role clears it.
  const isClinicRole = (roles.find((r) => r.name === role)?.permissions || [])
    .some((p) => CLINIC_ROLE_PERMISSIONS.includes(p)) || ['doctor', 'receptionist'].includes(role);
  useEffect(() => {
    onChange(isClinicRole && activeId ? [activeId] : []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, isClinicRole, activeId]);

  if (clinics.length === 0) return null;
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);

  return (
    <fieldset data-testid="clinic-ticks">
      <legend className="block text-xs font-medium text-gray-700 mb-1">Clinics they can open</legend>
      <ul className="space-y-1">
        {clinics.map((c) => (
          <li key={c.id} className="flex items-center gap-2">
            <input type="checkbox" id={`invite-clinic-${c.id}`} checked={value.includes(c.id)} onChange={() => toggle(c.id)}
              className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid={`invite-clinic-${c.id}`} />
            <label htmlFor={`invite-clinic-${c.id}`} className="text-sm text-gray-800">{c.name}</label>
          </li>
        ))}
      </ul>
      <p className="text-xs text-gray-500 mt-1">They get the role chosen above at each ticked clinic. You can change this later under Clinic access.</p>
    </fieldset>
  );
}
