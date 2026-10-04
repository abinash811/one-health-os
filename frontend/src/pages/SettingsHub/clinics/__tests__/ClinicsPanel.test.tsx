import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClinicsPanel from '../ClinicsPanel';
import { AuthContext } from '@/App';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const CLINIC = { id: 'c1', name: 'Sunrise Clinic', address: null, city: 'Pune', state: null, pincode: null,
  phone: '9876543210', email: null, registration_no: 'KMC-1', is_active: true, has_pharmacy: false };

const renderPanel = (user: unknown = { role: 'admin', permissions: ['*'] }) => render(
  <AuthContext.Provider value={{ user } as never}><ClinicsPanel /></AuthContext.Provider>,
);

describe('Clinics panel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.get as jest.Mock).mockResolvedValue({ data: [CLINIC] });
  });

  it('lists the hospital\'s clinics', async () => {
    renderPanel();
    expect(await screen.findByTestId('clinic-row-c1')).toHaveTextContent('Sunrise Clinic');
    expect(screen.getByTestId('clinic-row-c1')).toHaveTextContent('Pune');
  });

  it('points an empty hospital to Add clinic', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: [] });
    renderPanel();
    expect(await screen.findByText('No clinics yet')).toBeInTheDocument();
  });

  it('adds a clinic with only a name, then refreshes the list', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: CLINIC });
    renderPanel();
    await screen.findByTestId('clinic-row-c1');
    await userEvent.click(screen.getByTestId('add-clinic-btn'));
    expect(screen.getByTestId('clinic-save-btn')).toBeDisabled();
    await userEvent.type(screen.getByTestId('clinic-name'), 'North Clinic');
    await userEvent.click(screen.getByTestId('clinic-save-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('clinics', expect.objectContaining({ name: 'North Clinic' })));
    await waitFor(() => expect((api.get as jest.Mock).mock.calls.length).toBeGreaterThan(1));
  });

  it('edits a clinic', async () => {
    (api.put as jest.Mock).mockResolvedValue({ data: CLINIC });
    renderPanel();
    await userEvent.click(await screen.findByTestId('edit-clinic-c1'));
    await userEvent.clear(screen.getByTestId('clinic-city'));
    await userEvent.type(screen.getByTestId('clinic-city'), 'Mumbai');
    await userEvent.click(screen.getByTestId('clinic-save-btn'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('clinics/c1', expect.objectContaining({ city: 'Mumbai' })));
  });

  it('deactivates in one click, no confirmation (it can be undone)', async () => {
    (api.put as jest.Mock).mockResolvedValue({ data: { ...CLINIC, is_active: false } });
    renderPanel();
    await userEvent.click(await screen.findByTestId('toggle-clinic-c1'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('clinics/c1', { is_active: false }));
  });

  it('shows the server reason when a save is refused', async () => {
    const { toast } = jest.requireMock('sonner');
    (api.post as jest.Mock).mockRejectedValue(new Error("A clinic named 'North Clinic' already exists"));
    renderPanel();
    await userEvent.click(await screen.findByTestId('add-clinic-btn'));
    await userEvent.type(screen.getByTestId('clinic-name'), 'North Clinic');
    await userEvent.click(screen.getByTestId('clinic-save-btn'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("A clinic named 'North Clinic' already exists"));
  });

  it('is read-only for someone with only the view tick', async () => {
    renderPanel({ role: 'receptionist', permissions: ['clinics:view'] });
    await screen.findByTestId('clinic-row-c1');
    expect(screen.getByTestId('clinics-readonly-note')).toBeInTheDocument();
    expect(screen.queryByTestId('add-clinic-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('edit-clinic-c1')).not.toBeInTheDocument();
  });

  it('opens "Doctors at this clinic" from the row', async () => {
    renderPanel();
    await userEvent.click(await screen.findByTestId('clinic-doctors-c1'));
    expect(await screen.findByText('Doctors at Sunrise Clinic')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('clinics/c1/doctors');
  });

  it('shows the server reason when clinics cannot be loaded', async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error("Your role does not have the 'clinics:view' permission"));
    renderPanel();
    expect(await screen.findByText("Your role does not have the 'clinics:view' permission")).toBeInTheDocument();
  });
});
