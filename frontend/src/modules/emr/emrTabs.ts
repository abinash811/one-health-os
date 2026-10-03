/**
 * Tab bar shared by the EMR pages (Appointments / Calendar / Patients) — one definition so the keys and routes can't drift apart,
 * same reason as pages/inventoryTabs.js.
 */
import { ROUTES } from '@/constants/routes';

export const EMR_TABS = [
  { key: 'appointments', label: 'Appointments' },
  { key: 'calendar',     label: 'Calendar' },
  { key: 'patients',     label: 'Patients' },
];

const TAB_ROUTES: Record<string, string> = {
  appointments: ROUTES.EMR.APPOINTMENTS,
  calendar:     ROUTES.EMR.CALENDAR,
  patients:     ROUTES.EMR.PATIENTS,
};

export const emrTabRoute = (key: string): string => TAB_ROUTES[key] || ROUTES.EMR.APPOINTMENTS;
