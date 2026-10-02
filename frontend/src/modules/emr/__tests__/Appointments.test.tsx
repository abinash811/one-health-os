import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Appointments from '../pages/Appointments';
import CancelAppointmentDialog from '../components/CancelAppointmentDialog';
import api from '@/lib/axios';

// EMR step 1c (docs/28_EMR_SCOPE.md): the receptionist's day view + live queue.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const DOCTORS = [{ id: 'd1', name: 'Dr Rao', role: 'doctor' }];
const row = (over: Record<string, unknown>) => ({
  id: 'a1', patient_id: 'p1', patient_name: 'Asha Menon', doctor_user_id: 'd1', doctor_name: 'Dr Rao',
  appointment_date: '2026-10-05', start_time: '09:30', end_time: '10:00', token_number: 1,
  appointment_type: 'scheduled', status: 'booked', reason: 'Fever', cancel_reason: null, ...over,
});

function mockApi(rows: unknown[]) {
  (api.get as jest.Mock).mockImplementation((url: string) =>
    Promise.resolve({ data: url.startsWith('emr/doctors') ? DOCTORS : rows }));
}

const renderPage = () => render(<MemoryRouter><Appointments /></MemoryRouter>);

describe('Appointments queue', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows each visit with token, time, patient and status', async () => {
    mockApi([row({}), row({ id: 'a2', patient_name: 'Walk Inn', token_number: 2, start_time: null,
      appointment_type: 'walk_in', status: 'checked_in' })]);
    renderPage();

    await waitFor(() => expect(screen.getByTestId('queue-row-a1')).toBeInTheDocument());
    expect(screen.getByText('Asha Menon')).toBeInTheDocument();
    expect(screen.getByText('9:30 AM')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('Walk-in')).toBeInTheDocument();
    expect(screen.getByText('Checked In')).toBeInTheDocument();
  });

  it('shows an empty state with a booking action when the day is free', async () => {
    mockApi([]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/No appointments on/)).toBeInTheDocument());
  });

  it('the next-step button moves a booked visit to checked_in and refreshes', async () => {
    mockApi([row({})]);
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
    renderPage();

    await userEvent.click(await screen.findByTestId('queue-next-a1'));
    expect(api.post).toHaveBeenCalledWith('emr/appointments/a1/status', { status: 'checked_in' });
    await waitFor(() => expect((api.get as jest.Mock).mock.calls.length).toBeGreaterThan(2));
  });

  it('offers the right next step per status and none once a visit is done', async () => {
    mockApi([row({ id: 'w', status: 'checked_in' }), row({ id: 'c', status: 'in_consult' }),
      row({ id: 'd', status: 'completed' })]);
    renderPage();

    expect(await screen.findByTestId('queue-next-w')).toHaveTextContent('Start consult');
    expect(screen.getByTestId('queue-next-c')).toHaveTextContent('Complete');
    expect(screen.queryByTestId('queue-next-d')).not.toBeInTheDocument();
    expect(screen.queryByTestId('queue-more-d')).not.toBeInTheDocument();
  });

  it('shows the real server reason when a move is refused', async () => {
    const { toast } = jest.requireMock('sonner');
    mockApi([row({})]);
    (api.post as jest.Mock).mockRejectedValue(new Error('Cannot move an appointment from booked to completed'));
    renderPage();

    await userEvent.click(await screen.findByTestId('queue-next-a1'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Cannot move an appointment from booked to completed'));
  });
});

describe('CancelAppointmentDialog', () => {
  beforeEach(() => jest.clearAllMocks());

  it('cannot be confirmed without a reason, then posts it', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
    const onCancelled = jest.fn();
    render(<CancelAppointmentDialog appointment={row({}) as never} onClose={jest.fn()} onCancelled={onCancelled} />);

    const confirm = screen.getByTestId('confirm-cancel-btn');
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByTestId('cancel-reason-input'), 'Patient called');
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);

    expect(api.post).toHaveBeenCalledWith('emr/appointments/a1/status',
      { status: 'cancelled', cancel_reason: 'Patient called' });
    await waitFor(() => expect(onCancelled).toHaveBeenCalled());
  });
});
