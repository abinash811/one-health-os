import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SettingsPlaceBar from '../SettingsPlaceBar';
import { PlaceProvider } from '@/components/PlaceSwitcher';
import { AuthContext } from '@/App';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));

const CLINICS = [{ clinic_id: 'c1', clinic_name: 'Sunrise Clinic', role_name: 'admin', is_active: true }];
const STORES = [
  { pharmacy_id: 'p1', pharmacy_name: 'Main Street Pharmacy', role_name: 'admin', is_active: true },
  { pharmacy_id: 'p2', pharmacy_name: 'Station Road Pharmacy', role_name: 'admin', is_active: false },
];

function renderBar(moduleKey: string, clinics: unknown[] = CLINICS, stores: unknown[] = STORES, workspace: unknown = { name: 'Sharma Hospital' }) {
  (api.get as jest.Mock).mockImplementation((url: string) =>
    Promise.resolve({ data: url.startsWith('users/me/clinics') ? clinics : stores }));
  return render(
    <AuthContext.Provider value={{ user: { workspace } } as never}>
      <MemoryRouter><PlaceProvider><SettingsPlaceBar moduleKey={moduleKey} /></PlaceProvider></MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('Settings place bar', () => {
  beforeEach(() => jest.clearAllMocks());

  it('pharmacy settings name the pharmacy being edited', async () => {
    renderBar('pharmacy');
    expect(await screen.findByTestId('settings-place-name')).toHaveTextContent('Main Street Pharmacy');
    expect(screen.getByTestId('settings-place-bar')).toHaveTextContent('changes apply to this pharmacy only');
  });

  it('EMR settings name the clinic being edited', async () => {
    renderBar('emr');
    expect(await screen.findByTestId('settings-place-name')).toHaveTextContent('Sunrise Clinic');
    expect(screen.getByTestId('settings-place-bar')).toHaveTextContent('this clinic only');
  });

  it('with no clinic selected it says so and points to the fix', async () => {
    renderBar('emr', []);
    expect(await screen.findByText(/No clinic selected/)).toBeInTheDocument();
    expect(screen.getByTestId('settings-place-bar')).toHaveTextContent('Organisation → Clinics');
  });

  it('Organisation settings say they cover the whole organisation', async () => {
    renderBar('organisation');
    expect(await screen.findByTestId('settings-place-bar')).toHaveTextContent('your whole organisation — Sharma Hospital');
  });

  it('shows nothing for pharmacy settings outside the app shell (no place data)', () => {
    const { container } = render(
      <AuthContext.Provider value={{ user: null } as never}><SettingsPlaceBar moduleKey="pharmacy" /></AuthContext.Provider>);
    expect(container).toBeEmptyDOMElement();
  });
});
