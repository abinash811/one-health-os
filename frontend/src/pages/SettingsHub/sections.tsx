/**
 * The Settings hub's map: three modules (Organisation / EMR / Pharmacy), each with its sections.
 * One place decides who sees what, so adding a module's settings later is one entry here.
 * Access is shown from the user's real permission ticks (login sends them); the backend still
 * enforces every save.
 */
import React from 'react';
import { hasPermission } from '@/utils/clinicAccess';
import StoresTab from '@/pages/Settings/components/StoresTab';
import MembersTab from '@/pages/Team/components/MembersTab';
import RolesTab from '@/pages/Team/components/RolesTab';
import EmrSettingsPanel, { type EmrSettingsSection } from '@/modules/emr/components/EmrSettingsPanel';
import DoctorSchedulesPanel from '@/modules/emr/components/DoctorSchedulesPanel';
import PharmacyPanel, { type PharmacySection } from './PharmacyPanel';
import DoctorsPanel from './doctors/DoctorsPanel';

export interface HubUser {
  id?: string;
  role?: string;
  is_super_admin?: boolean;
  permissions?: string[];
}
export interface HubSection { key: string; label: string; allowed?: (u: HubUser) => boolean }
export interface HubModule {
  key: string;
  label: string;
  dot: string;
  allowed: (u: HubUser) => boolean;
  sections: HubSection[];
  content: (sectionKey: string, user: HubUser) => React.ReactNode;
}

export const isAdmin = (u: HubUser): boolean => u.role === 'admin' || !!u.is_super_admin;
/** An explicit tick — a session from before permissions were sent counts as "no tick". */
const ticked = (u: HubUser, permission: string): boolean => !!u.permissions && hasPermission(u.permissions, permission);

export const settingsPath = (module: string, section?: string): string =>
  `/settings/${module}${section ? `/${section}` : ''}`;

const EMR_FORM_SECTIONS = ['clinic-profile', 'id-formats', 'patient-form', 'doctors'];

export const HUB_MODULES: HubModule[] = [
  {
    key: 'organisation', label: 'Organisation', dot: 'bg-purple-600',
    allowed: (u) => isAdmin(u) || ticked(u, 'doctors:view'),
    sections: [
      { key: 'team', label: 'Team', allowed: isAdmin },
      { key: 'doctors', label: 'Doctors', allowed: (u) => isAdmin(u) || ticked(u, 'doctors:view') },
      { key: 'roles', label: 'Roles & Permissions', allowed: isAdmin },
      { key: 'stores', label: 'Stores & chain', allowed: isAdmin },
    ],
    content: (key, user) => (
      key === 'roles' ? <RolesTab />
        : key === 'stores' ? <StoresTab />
          : key === 'doctors' ? <DoctorsPanel />
            : <MembersTab currentUser={user} />
    ),
  },
  {
    key: 'emr', label: 'EMR', dot: 'bg-teal-600',
    allowed: (u) => isAdmin(u) || ticked(u, 'emr_settings:edit') || ticked(u, 'schedules:view'),
    sections: [
      { key: 'clinic-profile', label: 'Clinic profile' },
      { key: 'id-formats', label: 'Patient ID formats' },
      { key: 'patient-form', label: 'Patient form' },
      { key: 'doctors', label: 'Doctors & fees' },
      { key: 'schedules', label: 'Doctor schedules', allowed: (u) => isAdmin(u) || ticked(u, 'schedules:view') },
    ],
    // The form panel stays mounted (just hidden) while Doctor schedules is open, so unsaved edits survive the switch.
    content: (key) => (
      <>
        <div className={key === 'schedules' ? 'hidden' : ''}>
          <EmrSettingsPanel section={(EMR_FORM_SECTIONS.includes(key) ? key : 'clinic-profile') as EmrSettingsSection} />
        </div>
        {key === 'schedules' && <DoctorSchedulesPanel />}
      </>
    ),
  },
  {
    key: 'pharmacy', label: 'Pharmacy', dot: 'bg-brand',
    allowed: isAdmin,
    sections: [
      { key: 'profile', label: 'Pharmacy profile' },
      { key: 'receipt', label: 'Receipt & print' },
      { key: 'gst', label: 'Tax & GST' },
      { key: 'notifications', label: 'Notifications' },
      { key: 'inventory', label: 'Inventory' },
      { key: 'billing', label: 'Billing' },
      { key: 'bill-sequence', label: 'Bill sequence' },
      { key: 'returns', label: 'Returns' },
      { key: 'backup', label: 'Data & backup' },
    ],
    content: (key) => <PharmacyPanel section={key as PharmacySection} />,
  },
];

/** The modules this user may open, each with only the sections they may see. */
export const visibleModules = (user: HubUser | null | undefined) => {
  const u = user || {};
  return HUB_MODULES.filter((m) => m.allowed(u)).map((m) => ({
    ...m, sections: m.sections.filter((s) => !s.allowed || s.allowed(u)),
  })).filter((m) => m.sections.length > 0);
};
