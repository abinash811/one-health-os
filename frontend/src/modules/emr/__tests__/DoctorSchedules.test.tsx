import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DoctorSchedules from '../components/DoctorSchedulesPanel';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const BLOCK = { id: 'b1', doctor_user_id: 'd1', weekday: 0, start_time: '09:00', end_time: '13:00',
  slot_minutes: 15, is_active: true };

function mockApi(doctors: unknown[], blocks: unknown[]) {
  (api.get as jest.Mock).mockImplementation((url: string) =>
    Promise.resolve({ data: url.startsWith('emr/doctors') ? doctors : blocks }));
}
const renderPage = () => render(<DoctorSchedules />);

describe('Doctor Schedules', () => {
  beforeEach(() => jest.clearAllMocks());

  it('lays out the week with working hours and "Not working" days', async () => {
    mockApi([{ id: 'd1', name: 'Dr Rao', role: 'doctor' }], [BLOCK]);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('block-b1')).toHaveTextContent('9:00 AM – 1:00 PM · 15 min'));
    expect(screen.getByTestId('schedule-day-1')).toHaveTextContent('Not working');
    expect(api.get).toHaveBeenCalledWith('emr/schedules?doctor_user_id=d1');
  });

  it('points a clinic with no doctors to Team', async () => {
    mockApi([], []);
    renderPage();
    await waitFor(() => expect(screen.getByText('No doctors yet', { selector: 'h3' })).toBeInTheDocument());
    expect(screen.getByTestId('add-hours-btn')).toBeDisabled();
  });

  it('adds working hours for the chosen doctor', async () => {
    mockApi([{ id: 'd1', name: 'Dr Rao', role: 'doctor' }], []);
    (api.post as jest.Mock).mockResolvedValue({ data: BLOCK });
    renderPage();

    await waitFor(() => expect(screen.getByTestId('add-hours-btn')).toBeEnabled());
    await userEvent.click(screen.getByTestId('add-hours-btn'));
    await userEvent.click(await screen.findByTestId('submit-block-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('emr/schedules', {
      doctor_user_id: 'd1', weekday: 0, start_time: '09:00', end_time: '13:00', slot_minutes: 15,
    }));
  });

  it('removes a block only after confirming', async () => {
    mockApi([{ id: 'd1', name: 'Dr Rao', role: 'doctor' }], [BLOCK]);
    (api.delete as jest.Mock).mockResolvedValue({ data: {} });
    renderPage();

    await userEvent.click(await screen.findByTestId('delete-block-b1'));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('emr/schedules/b1'));
  });
});
