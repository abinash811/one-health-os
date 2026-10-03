/**
 * Sidebar nav + role badge config, split out of Layout.js (300-line rule).
 * `roles` lists the role names that see an item; a route's real access
 * control is still the backend permission check.
 */
import {
  LayoutDashboard, ShoppingCart, Package, ShoppingBag, Users, FileText, Settings,
  UserCog, CalendarDays, CalendarRange, Stethoscope, Receipt,
} from 'lucide-react';

// ── Nav definition: one folding section per MODULE ───────────────────────────
// `prefixes` = every URL that belongs to the module (so e.g. the consultation page opens EMR even
// though it has no sidebar item). `dot` = the module's colour chip.
export const NAV_MODULES = [
  {
    id: 'emr', label: 'EMR', dot: 'bg-teal-600',
    prefixes: ['/emr', '/patient-billing'],
    items: [
      { name: 'Appointments', path: '/emr/appointments', icon: CalendarDays, roles: ['admin', 'receptionist', 'doctor'] },
      { name: 'Calendar',     path: '/emr/calendar',     icon: CalendarRange, roles: ['admin', 'receptionist', 'doctor'] },
      { name: 'Patients',     path: '/emr/patients',     icon: Stethoscope,  roles: ['admin', 'receptionist', 'doctor'] },
      { name: 'Clinic Billing', path: '/patient-billing', icon: Receipt,     roles: ['admin', 'receptionist', 'doctor'] },
    ],
  },
  {
    id: 'pharmacy', label: 'Pharmacy', dot: 'bg-brand',
    prefixes: ['/dashboard', '/billing', '/inventory', '/purchases', '/customers', '/suppliers', '/reports', '/compliance'],
    items: [
      { name: 'Dashboard',  path: '/dashboard',  icon: LayoutDashboard, roles: ['admin', 'manager', 'cashier', 'inventory_staff'] },
      { name: 'Billing',    path: '/billing',    icon: ShoppingCart,    roles: ['admin', 'manager', 'cashier'] },
      { name: 'Inventory',  path: '/inventory',  icon: Package,         roles: ['admin', 'manager', 'cashier', 'inventory_staff'] },
      { name: 'Purchases',  path: '/purchases',  icon: ShoppingBag,     roles: ['admin', 'manager', 'inventory_staff'] },
      { name: 'Customers',  path: '/customers',  icon: Users,           roles: ['admin', 'manager', 'cashier'] },
      { name: 'Suppliers',  path: '/suppliers',  icon: ShoppingBag,     roles: ['admin', 'manager', 'inventory_staff'] },
      { name: 'Reports',    path: '/reports',    icon: FileText,        roles: ['admin', 'manager'] },
      { name: 'Sch H1 Register', path: '/compliance/schedule-h1', icon: FileText, roles: ['admin', 'manager'] },
    ],
  },
  {
    id: 'admin', label: 'Admin', dot: 'bg-purple-600',
    prefixes: ['/settings', '/team', '/audit-log'],
    items: [
      { name: 'Audit Log', path: '/audit-log', icon: FileText, roles: ['admin'] },
      { name: 'Settings',  path: '/settings',  icon: Settings, roles: ['admin'] },
      { name: 'Team',      path: '/team',      icon: UserCog,  roles: ['admin'] },
    ],
  },
];

/** Which module a URL belongs to (null = none, e.g. an unknown page). */
export const moduleForPath = (pathname) => NAV_MODULES.find((m) =>
  m.prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`)))?.id ?? null;

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

/**
 * The sidebar modules this user sees. An administrator (the Team checkbox, or a wildcard role) gets
 * everything whatever their clinical role is — a Doctor who is also an admin sees Team and Settings too.
 * A module with nothing the user may open is dropped entirely.
 */
export const visibleNavModules = (user) => NAV_MODULES.map((m) => ({
  ...m,
  items: m.items.filter((i) => user?.is_admin || user?.is_super_admin || i.roles.includes(user?.role)),
})).filter((m) => m.items.length > 0);
