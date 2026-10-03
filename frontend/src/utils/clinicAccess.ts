import { useContext } from 'react';
import { AuthContext } from '@/App';
import { USER_ROLE } from '@/constants/domainConstants';

/**
 * Which clinic buttons to OFFER the current user. The frontend only knows the user's role name (the
 * login response carries no permission list yet), so this hides the actions the built-in roles can't do
 * — the backend still enforces the real permission on every call, and a custom role simply sees the
 * button and gets a clear refusal. One place to change when the login response carries permissions.
 *   doctor        — views billing, writes prescriptions, never takes money
 *   receptionist  — runs the desk and takes money, never cancels invoices or writes prescriptions
 *   admin (checkbox) / other — everything
 */
export function useClinicAccess() {
  const auth = useContext(AuthContext) as unknown as { user: { role: string; is_super_admin?: boolean } | null } | null;
  const role = auth?.user?.role;
  // An admin (checkbox) keeps their clinical role but gets everything.
  if (auth?.user?.is_super_admin) return { canCollect: true, canCancelInvoice: true, canWriteRx: true };
  return {
    canCollect: role !== USER_ROLE.DOCTOR,
    canCancelInvoice: role !== USER_ROLE.DOCTOR && role !== USER_ROLE.RECEPTIONIST,
    canWriteRx: role !== USER_ROLE.RECEPTIONIST,
  };
}
