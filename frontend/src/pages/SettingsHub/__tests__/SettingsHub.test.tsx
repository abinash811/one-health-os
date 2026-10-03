import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import SettingsHub from '../index';
import { visibleModules } from '../sections';
import { AuthContext } from '@/App';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const FORM = { phone: 'optional', alternate_phone: 'optional', age: 'optional', date_of_birth: 'optional',
  gender: 'optional', blood_group: 'optional', city: 'optional', allergies: 'optional', notes: 'optional' };
const EMR_SETTINGS = { clinic_name: null, clinic_address: null, clinic_phone: null, clinic_email: null,
  registration_no: null, rx_footer: null, rx_prefix: 'RX-', uhid_prefix: 'UH-', uhid_digits: 6, uhid_next: 8,
  default_slot_minutes: 15, patient_form: FORM, fallback: { clinic_name: 'Sunrise Pharmacy' } };

function mockApi() {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('emr/settings')) return Promise.resolve({ data: EMR_SETTINGS });
    if (url.startsWith('emr/doctors')) return Promise.resolve({ data: [{ id: 'd1', name: 'Dr Rao', role: 'doctor' }] });
    if (url.startsWith('emr/schedules')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
}

const Where = () => <div data-testid="where">{useLocation().pathname}</div>;
const renderAt = (path: string, user: unknown) => render(
  <AuthContext.Provider value={{ user } as never}>
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings" element={<><SettingsHub /><Where /></>} />
        <Route path="/settings/:module" element={<><SettingsHub /><Where /></>} />
        <Route path="/settings/:module/:section" element={<><SettingsHub /><Where /></>} />
      </Routes>
    </MemoryRouter>
  </AuthContext.Provider>,
);

const ADMIN = { role: 'admin', is_super_admin: true, permissions: ['*'] };
const tabNames = () => screen.getAllByRole('tab').map((t) => t.textContent);

describe('visibleModules — who sees which settings', () => {
  it('an administrator sees all three modules', () => {
    expect(visibleModules(ADMIN).map((m) => m.key)).toEqual(['organisation', 'emr', 'pharmacy']);
  });
  it('a clinic manager ticked for EMR settings sees only EMR, without Doctor schedules unless ticked', () => {
    const mods = visibleModules({ role: 'clinic_manager', permissions: ['emr_settings:edit'] });
    expect(mods.map((m) => m.key)).toEqual(['emr']);
    expect(mods[0].sections.map((s) => s.key)).not.toContain('schedules');
  });
  it('a doctor with schedule access sees EMR only', () => {
    const mods = visibleModules({ role: 'doctor', permissions: ['schedules:view', 'schedules:edit'] });
    expect(mods.map((m) => m.key)).toEqual(['emr']);
    expect(mods[0].sections.map((s) => s.key)).toContain('schedules');
  });
  it('someone with no settings ticks, or an old session without a permission list, sees nothing', () => {
    expect(visibleModules({ role: 'cashier', permissions: ['billing:create'] })).toEqual([]);
    expect(visibleModules({ role: 'receptionist' })).toEqual([]);
    expect(visibleModules(null)).toEqual([]);
  });
});

describe('Settings hub', () => {
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('/settings opens the first module and section', async () => {
    renderAt('/settings', ADMIN);
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/settings/organisation/team'));
    expect(tabNames()).toEqual(['Organisation', 'EMR', 'Pharmacy']);
    expect(screen.getByTestId('settings-nav-roles')).toBeInTheDocument();
  });

  it('a module tab lists only that module\'s sections', async () => {
    renderAt('/settings/emr', ADMIN);
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/settings/emr/clinic-profile'));
    expect(screen.getByTestId('settings-nav-doctors')).toBeInTheDocument();
    expect(screen.getByTestId('settings-nav-schedules')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-nav-gst')).not.toBeInTheDocument();
  });

  it('a deep link opens that exact section; an unknown section falls back to the first', async () => {
    const { unmount } = renderAt('/settings/emr/schedules', ADMIN);
    expect(await screen.findByTestId('emr-schedules-page')).toBeInTheDocument();
    unmount();
    renderAt('/settings/emr/nonsense', ADMIN);
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/settings/emr/clinic-profile'));
  });

  it('a user may not open a module they have no access to — they land on their own', async () => {
    renderAt('/settings/pharmacy/gst', { role: 'clinic_manager', permissions: ['emr_settings:edit'] });
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/settings/emr/clinic-profile'));
    expect(tabNames()).toEqual(['EMR']);
  });

  it('shows Access Denied when nothing is allowed', () => {
    renderAt('/settings', { role: 'cashier', permissions: ['billing:create'] });
    expect(screen.getByTestId('settings-denied')).toBeInTheDocument();
  });

  it('keeps unsaved clinic edits when you visit Doctor schedules and come back', async () => {
    renderAt('/settings/emr/clinic-profile', ADMIN);
    const name = await screen.findByTestId('set-clinic_name');
    await userEvent.type(name, 'Sunrise Clinic');
    await userEvent.click(screen.getByTestId('settings-nav-schedules'));
    expect(await screen.findByTestId('emr-schedules-page')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('settings-nav-clinic-profile'));
    expect(await screen.findByTestId('set-clinic_name')).toHaveValue('Sunrise Clinic');
  });

  it('the Change History shortcut is for administrators only', async () => {
    const { unmount } = renderAt('/settings/emr', ADMIN);
    expect(await screen.findByTestId('settings-history-btn')).toBeInTheDocument();
    unmount();
    renderAt('/settings/emr', { role: 'doctor', permissions: ['schedules:view'] });
    await screen.findByTestId('settings-hub');
    expect(screen.queryByTestId('settings-history-btn')).not.toBeInTheDocument();
  });
});
