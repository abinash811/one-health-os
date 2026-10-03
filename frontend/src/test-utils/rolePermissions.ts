/** What the built-in clinic roles are ticked for by default (backend/constants.py DEFAULT_ROLES) — what login sends as `permissions`. */
export const DEFAULT_ROLE_PERMISSIONS: Record<string, string[]> = {
  doctor: ['patient_billing:view', 'prescriptions:view', 'prescriptions:create', 'prescriptions:edit', 'prescriptions:issue', 'prescriptions:cancel'],
  receptionist: ['patient_billing:view', 'patient_billing:charge', 'patient_billing:invoice', 'patient_billing:collect', 'prescriptions:view'],
  admin: ['*'],
};

export const userFor = (role: string) => ({ role, permissions: DEFAULT_ROLE_PERMISSIONS[role] });
