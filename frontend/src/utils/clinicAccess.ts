import { useContext } from 'react';
import { AuthContext } from '@/App';

/** Does this permission list (as /auth/me and login send it) allow `permission`? `*` = everything. */
export const hasPermission = (permissions: string[] | undefined | null, permission: string): boolean =>
  !permissions || permissions.includes('*') || permissions.includes(permission);

/**
 * Which clinic buttons to OFFER the current user — straight from the Roles & Permissions ticks the
 * login response carries, never from the role's name. "Anyone can create a bill if access is given":
 * tick Collect Payments on any role and its users see the button. An old session without the list
 * shows everything (the backend still refuses what the role can't do, with the reason).
 */
export function useClinicAccess() {
  const auth = useContext(AuthContext) as unknown as { user: { permissions?: string[] } | null } | null;
  const perms = auth?.user?.permissions;
  return {
    canCollect: hasPermission(perms, 'patient_billing:collect'),
    canCancelInvoice: hasPermission(perms, 'patient_billing:void'),
    canWriteRx: hasPermission(perms, 'prescriptions:create'),
  };
}
