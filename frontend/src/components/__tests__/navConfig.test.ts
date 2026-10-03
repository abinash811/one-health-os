import { visibleNavGroups } from '../navConfig';

const names = (user: unknown) => visibleNavGroups(user).flatMap((g: { items: { name: string }[] }) => g.items.map((i) => i.name));

describe('visibleNavGroups', () => {
  it('a doctor sees the clinic pages but not Team or Settings', () => {
    const n = names({ role: 'doctor' });
    expect(n).toContain('Calendar');
    expect(n).not.toContain('Team');
    expect(n).not.toContain('Settings');
  });

  it('a doctor who is also an administrator sees Team and Settings too', () => {
    const n = names({ role: 'doctor', is_admin: true });
    expect(n).toEqual(expect.arrayContaining(['Calendar', 'Team', 'Settings', 'Billing']));
  });

  it('a wildcard "Super Admin" role sees everything', () => {
    expect(names({ role: 'custom', is_super_admin: true })).toContain('Team');
  });

  it('drops empty groups', () => {
    expect(visibleNavGroups({ role: 'unknown-role' })).toEqual([]);
  });
});
