/**
 * Tab bar shared by the EMR pages (Appointments / Calendar / Patients / Doctor
 * Schedules / Settings) — one definition so the keys and routes can't drift apart,
 * same reason as pages/inventoryTabs.js.
 */
import { ROUTES } from '@/constants/routes';

export const EMR_TABS = [
  { key: 'appointments', label: 'Appointments' },
  { key: 'calendar',     label: 'Calendar' },
  { key: 'patients',     label: 'Patients' },
  { key: 'schedules',    label: 'Doctor Schedules' },
  { key: 'settings',     label: 'Settings' },
];

const TAB_ROUTES: Record<string, string> = {
  appointments: ROUTES.EMR.APPOINTMENTS,
  calendar:     ROUTES.EMR.CALENDAR,
  patients:     ROUTES.EMR.PATIENTS,
  schedules:    ROUTES.EMR.SCHEDULES,
  settings:     ROUTES.EMR.SETTINGS,
};

export const emrTabRoute = (key: string): string => TAB_ROUTES[key] || ROUTES.EMR.APPOINTMENTS;
