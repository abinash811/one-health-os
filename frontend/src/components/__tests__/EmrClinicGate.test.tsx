import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import api from '@/lib/axios';
import EmrClinicGate from '../EmrClinicGate';
import { PlaceProvider } from '../PlaceSwitcher';

jest.mock('@/lib/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
const mockApi = api as unknown as { get: jest.Mock; post: jest.Mock };

const clinic = (id: string, active: boolean) => ({ clinic_id: id, clinic_name: `Clinic ${id}`, role_name: 'admin', is_active: active });
const setup = (clinics: unknown[], user: object) => {
  mockApi.get.mockImplementation((url: string) => Promise.resolve({ data: url.includes('clinics') ? clinics : [] }));
  return render(
    <MemoryRouter initialEntries={['/emr/patients']}>
      <PlaceProvider>
        <Routes>
          <Route element={<EmrClinicGate user={user as never} />}>
            <Route path="/emr/patients" element={<div>patients page</div>} />
          </Route>
        </Routes>
      </PlaceProvider>
    </MemoryRouter>);
};

describe('EmrClinicGate', () => {
  it('shows the page when a clinic is active', async () => {
    setup([clinic('a', true)], { role: 'admin' });
    expect(await screen.findByText('patients page')).toBeInTheDocument();
  });

  it('lets you pick a clinic when none is active', async () => {
    mockApi.post.mockResolvedValue({ data: {} });
    setup([clinic('a', false), clinic('b', false)], { role: 'receptionist' });
    await userEvent.click(await screen.findByTestId('gate-clinic-b'));
    expect(mockApi.post).toHaveBeenCalledWith(expect.stringContaining('switch-clinic'), { clinic_id: 'b' });
  });

  it('sends an admin with no clinics to add one', async () => {
    setup([], { role: 'admin' });
    expect(await screen.findByTestId('gate-add-clinic')).toHaveAttribute('href', '/settings/organisation/clinics');
  });

  it('tells a non-admin with no clinics to ask an administrator', async () => {
    setup([], { role: 'receptionist', permissions: [] });
    expect(await screen.findByText(/Ask an administrator/)).toBeInTheDocument();
  });
});
