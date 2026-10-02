/**
 * Tab bar shared by the three EMR pages (Appointments / Patients / Doctor
 * Schedules) — one definition so the keys and routes can't drift apart,
 * same reason as pages/inventoryTabs.js.
 */
import { ROUTES } from '@/constants/routes';

export const EMR_TABS = [
  { key: 'appointments', label: 'Appointments' },
  { key: 'patients',     label: 'Patients' },
  { key: 'schedules',    label: 'Doctor Schedules' },
];

const TAB_ROUTES: Record<string, string> = {
  appointments: ROUTES.EMR.APPOINTMENTS,
  patients:     ROUTES.EMR.PATIENTS,
  schedules:    ROUTES.EMR.SCHEDULES,
};

export const emrTabRoute = (key: string): string => TAB_ROUTES[key] || ROUTES.EMR.APPOINTMENTS;
