import { moduleForPath, visibleNavModules } from '../navConfig';

type Mod = { id: string; label: string; items: { name: string }[] };
const mods = (user: unknown) => visibleNavModules(user) as Mod[];
const names = (user: unknown) => mods(user).flatMap((m) => m.items.map((i) => i.name));

describe('visibleNavModules', () => {
  it('a doctor sees only the EMR module — no Pharmacy, no Admin', () => {
    expect(mods({ role: 'doctor' }).map((m) => m.id)).toEqual(['emr']);
    expect(names({ role: 'doctor' })).toEqual(['Appointments', 'Calendar', 'Patients', 'Clinic Billing']);
  });

  it('a cashier sees only Pharmacy, and only what a cashier may open', () => {
    expect(mods({ role: 'cashier' }).map((m) => m.id)).toEqual(['pharmacy']);
    expect(names({ role: 'cashier' })).toEqual(expect.arrayContaining(['Billing', 'Customers']));
    expect(names({ role: 'cashier' })).not.toContain('Purchases');
  });

  it('a doctor who is also an administrator sees all three modules', () => {
    expect(mods({ role: 'doctor', is_admin: true }).map((m) => m.id)).toEqual(['emr', 'pharmacy', 'admin']);
    expect(names({ role: 'doctor', is_admin: true })).toEqual(expect.arrayContaining(['Calendar', 'Team', 'Settings', 'Billing']));
  });

  it('a wildcard "Super Admin" role sees everything', () => {
    expect(names({ role: 'custom', is_super_admin: true })).toContain('Team');
  });

  it('drops modules with nothing to show', () => {
    expect(visibleNavModules({ role: 'unknown-role' })).toEqual([]);
  });

  it('keeps Audit Log under Admin, Sch H1 Register under Pharmacy', () => {
    const all = mods({ role: 'admin', is_admin: true });
    expect(all.find((m) => m.id === 'admin')!.items.map((i) => i.name)).toEqual(['Audit Log', 'Settings', 'Team']);
    expect(all.find((m) => m.id === 'pharmacy')!.items.map((i) => i.name)).toContain('Sch H1 Register');
  });
});

describe('moduleForPath', () => {
  it('opens the module a page belongs to, including pages with no sidebar item', () => {
    expect(moduleForPath('/emr/consult/abc')).toBe('emr');
    expect(moduleForPath('/emr/settings')).toBe('emr');
    expect(moduleForPath('/patient-billing/pending')).toBe('emr');
    expect(moduleForPath('/billing/create')).toBe('pharmacy');
    expect(moduleForPath('/inventory/product/SKU1')).toBe('pharmacy');
    expect(moduleForPath('/compliance/schedule-h1')).toBe('pharmacy');
    expect(moduleForPath('/team')).toBe('admin');
  });
  it('does not confuse similar prefixes, and returns null for unknown pages', () => {
    expect(moduleForPath('/billing-other')).toBeNull();
    expect(moduleForPath('/nowhere')).toBeNull();
  });
});
