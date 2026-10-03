/**
 * Sidebar nav + role badge config, split out of Layout.js (300-line rule).
 * `roles` lists the role names that see an item; a route's real access
 * control is still the backend permission check.
 */
import {
  LayoutDashboard, ShoppingCart, Package, ShoppingBag, Users, FileText, Settings,
  UserCog, CalendarDays, CalendarRange, Stethoscope, Receipt,
} from 'lucide-react';

// ── Nav definition with group labels ─────────────────────────────────────────
export const NAV_GROUPS = [
  {
    label: 'CLINIC',
    items: [
      { name: 'Appointments', path: '/emr/appointments', icon: CalendarDays, roles: ['admin', 'receptionist', 'doctor'] },
      { name: 'Calendar',     path: '/emr/calendar',     icon: CalendarRange, roles: ['admin', 'receptionist', 'doctor'] },
      { name: 'Patients',     path: '/emr/patients',     icon: Stethoscope,  roles: ['admin', 'receptionist', 'doctor'] },
      { name: 'Clinic Billing', path: '/patient-billing', icon: Receipt,     roles: ['admin', 'receptionist', 'doctor'] },
    ],
  },
  {
    label: 'DAILY OPS',
    items: [
      { name: 'Dashboard',  path: '/dashboard',  icon: LayoutDashboard, roles: ['admin', 'manager', 'cashier', 'inventory_staff'] },
      { name: 'Billing',    path: '/billing',    icon: ShoppingCart,    roles: ['admin', 'manager', 'cashier'] },
      { name: 'Inventory',  path: '/inventory',  icon: Package,         roles: ['admin', 'manager', 'cashier', 'inventory_staff'] },
      { name: 'Purchases',  path: '/purchases',  icon: ShoppingBag,     roles: ['admin', 'manager', 'inventory_staff'] },
    ],
  },
  {
    label: 'RELATIONSHIPS',
    items: [
      { name: 'Customers', path: '/customers', icon: Users,     roles: ['admin', 'manager', 'cashier'] },
      { name: 'Suppliers', path: '/suppliers', icon: ShoppingBag, roles: ['admin', 'manager', 'inventory_staff'] },
    ],
  },
  {
    label: 'REPORTS',
    items: [
      { name: 'Reports', path: '/reports', icon: FileText, roles: ['admin', 'manager'] },
    ],
  },
  {
    label: 'COMPLIANCE',
    items: [
      { name: 'Sch H1 Register', path: '/compliance/schedule-h1', icon: FileText, roles: ['admin', 'manager'] },
      { name: 'Audit Log',       path: '/audit-log',              icon: FileText, roles: ['admin'] },
    ],
  },
  {
    label: 'ADMIN',
    items: [
      { name: 'Settings', path: '/settings', icon: Settings, roles: ['admin'] },
      { name: 'Team',     path: '/team',     icon: UserCog,  roles: ['admin'] },
    ],
  },
];

// ── Role badge (muted colors per spec) ────────────────────────────────────────
export const ROLE_BADGE = {
  admin:           'bg-purple-50 text-purple-700',
  manager:         'bg-blue-50   text-blue-700',
  cashier:         'bg-green-50  text-green-700',
  inventory_staff: 'bg-orange-50 text-orange-700',
  receptionist:    'bg-teal-50   text-teal-700',
  doctor:          'bg-sky-50    text-sky-700',
};
export const ROLE_LABEL = {
  admin: 'Admin', manager: 'Manager', cashier: 'Cashier', inventory_staff: 'Inventory',
  receptionist: 'Reception', doctor: 'Doctor',
};
