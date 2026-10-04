import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import api from '@/lib/axios';
import PlaceSwitcher, { PlaceProvider } from '../PlaceSwitcher';

jest.mock('@/lib/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

// The top-bar switcher (docs/32 P2): one list, clinics and pharmacies, the active one ticked.
const CLINICS = [
  { clinic_id: 'c1', clinic_name: 'Sunrise Clinic', role_name: 'doctor', is_active: true },
  { clinic_id: 'c2', clinic_name: 'North Clinic', role_name: 'doctor', is_active: false },
];
const STORES = [
  { pharmacy_id: 'p1', pharmacy_name: 'Main Pharmacy', role_name: 'admin', is_active: true },
  { pharmacy_id: 'p2', pharmacy_name: 'Second Pharmacy', role_name: 'manager', is_active: false },
];

const mockApi = (clinics: unknown[] = CLINICS, stores: unknown[] = STORES) => {
  (api.get as jest.Mock).mockImplementation((url: string) =>
    Promise.resolve({ data: url.startsWith('users/me/clinics') ? clinics : stores }));
};
const renderAt = (path: string) => render(
  <MemoryRouter initialEntries={[path]}><PlaceProvider><PlaceSwitcher /></PlaceProvider></MemoryRouter>);

describe('PlaceSwitcher outside the app shell', () => {
  it('renders nothing without a provider (a page on its own)', () => {
    const { container } = render(<MemoryRouter><PlaceSwitcher /></MemoryRouter>);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('PlaceSwitcher', () => {
  const reload = jest.fn();
  beforeAll(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: { ...window.location, reload } });
  });
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('shows the active clinic on EMR pages and the active pharmacy elsewhere', async () => {
    const { unmount } = renderAt('/emr/appointments');
    expect(await screen.findByText('Sunrise Clinic')).toBeInTheDocument();
    unmount();
    renderAt('/billing');
    expect(await screen.findByText('Main Pharmacy')).toBeInTheDocument();
  });

  it('lists clinics and pharmacies in two groups', async () => {
    renderAt('/emr/appointments');
    await screen.findByText('Sunrise Clinic');
    await userEvent.click(screen.getByTestId('place-switcher-trigger'));
    expect(await screen.findByTestId('place-option-clinic-c2')).toBeInTheDocument();
    expect(screen.getByTestId('place-option-pharmacy-p2')).toBeInTheDocument();
    expect(screen.getByText('Clinics')).toBeInTheDocument();
    expect(screen.getByText('Pharmacies')).toBeInTheDocument();
  });

  it('switching clinic calls the clinic endpoint, then reloads', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
    renderAt('/emr/appointments');
    await screen.findByText('Sunrise Clinic');
    await userEvent.click(screen.getByTestId('place-switcher-trigger'));
    await userEvent.click(await screen.findByTestId('place-option-clinic-c2'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('users/me/switch-clinic', { clinic_id: 'c2' }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it('switching pharmacy calls the store endpoint', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
    renderAt('/billing');
    await screen.findByText('Main Pharmacy');
    await userEvent.click(screen.getByTestId('place-switcher-trigger'));
    await userEvent.click(await screen.findByTestId('place-option-pharmacy-p2'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('users/me/switch-store', { pharmacy_id: 'p2' }));
  });

  it('clicking the place you are already at does nothing', async () => {
    renderAt('/emr/appointments');
    await screen.findByText('Sunrise Clinic');
    await userEvent.click(screen.getByTestId('place-switcher-trigger'));
    await userEvent.click(await screen.findByTestId('place-option-clinic-c1'));
    expect(api.post).not.toHaveBeenCalled();
  });

  it('with no clinic, says so and points to where to add one', async () => {
    mockApi([], STORES);
    renderAt('/emr/appointments');
    expect(await screen.findByText('Select a clinic')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('place-switcher-trigger'));
    expect(await screen.findByTestId('place-switcher-no-clinics')).toHaveTextContent('Settings → Organisation → Clinics');
  });

  it('shows the server reason when switching fails', async () => {
    const { toast } = jest.requireMock('sonner');
    (api.post as jest.Mock).mockRejectedValue(new Error('You do not have access to that clinic'));
    renderAt('/emr/appointments');
    await screen.findByText('Sunrise Clinic');
    await userEvent.click(screen.getByTestId('place-switcher-trigger'));
    await userEvent.click(await screen.findByTestId('place-option-clinic-c2'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('You do not have access to that clinic'));
    expect(reload).not.toHaveBeenCalled();
  });
});
