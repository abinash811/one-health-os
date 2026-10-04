import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClinicAccessModal from '../ClinicAccessModal';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const CLINICS = [{ id: 'c1', name: 'Sunrise Clinic', city: 'Pune' }, { id: 'c2', name: 'North Clinic', city: null }];
const ROLES = [{ name: 'doctor', display_name: 'Doctor (EMR)' }, { name: 'receptionist', display_name: 'Receptionist (EMR)' }];
const MEMBER = { id: 'u1', name: 'Asha' };

function mockApi(grants: unknown[] = []) {
  (api.get as jest.Mock).mockImplementation((url: string) => Promise.resolve({
    data: url.startsWith('clinics') ? CLINICS : url.startsWith('roles') ? ROLES : grants }));
}
const renderIt = () => render(<ClinicAccessModal member={MEMBER} open onClose={jest.fn()} />);

describe('Clinic access (Team)', () => {
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('lists every clinic of the workspace with a role to grant', async () => {
    renderIt();
    expect(await screen.findByText('Sunrise Clinic')).toBeInTheDocument();
    expect(screen.getByText('North Clinic')).toBeInTheDocument();
    expect(screen.getByTestId('clinic-role-c1')).toHaveValue('receptionist');
  });

  it('grants access with the chosen role, then reloads', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
    renderIt();
    await userEvent.selectOptions(await screen.findByTestId('clinic-role-c1'), 'doctor');
    await userEvent.click(screen.getByTestId('grant-clinic-c1'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('users/u1/clinic-access', { clinic_id: 'c1', role: 'doctor' }));
  });

  it('shows the role they hold and lets you revoke', async () => {
    mockApi([{ clinic_id: 'c1', clinic_name: 'Sunrise Clinic', role_name: 'doctor' }]);
    (api.delete as jest.Mock).mockResolvedValue({ data: {} });
    renderIt();
    await userEvent.click(await screen.findByTestId('revoke-clinic-c1'));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('users/u1/clinic-access/c1'));
  });

  it('shows the server reason when a grant is refused', async () => {
    const { toast } = jest.requireMock('sonner');
    (api.post as jest.Mock).mockRejectedValue(new Error('Role \'x\' not found'));
    renderIt();
    await userEvent.click(await screen.findByTestId('grant-clinic-c2'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Role 'x' not found"));
  });

  it('points to Settings when the workspace has no clinic yet', async () => {
    (api.get as jest.Mock).mockImplementation((url: string) => Promise.resolve({ data: url.startsWith('roles') ? ROLES : [] }));
    renderIt();
    expect(await screen.findByText(/Add a clinic under Settings/)).toBeInTheDocument();
  });
});
