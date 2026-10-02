import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BookAppointmentModal from '../components/BookAppointmentModal';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const DOCTORS = [{ id: 'd1', name: 'Dr Rao', role: 'doctor' }];
const PATIENT = { id: 'p1', name: 'Asha Menon', phone: '9876543210' };
const SLOTS = [
  { start_time: '09:00', end_time: '09:30', available: false },
  { start_time: '09:30', end_time: '10:00', available: true },
];

function setup() {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('emr/slots')) return Promise.resolve({ data: SLOTS });
    return Promise.resolve({ data: { data: [PATIENT] } });
  });
  (api.post as jest.Mock).mockResolvedValue({ data: { token_number: 3 } });
  const onBooked = jest.fn();
  render(<BookAppointmentModal open doctors={DOCTORS} defaultDoctorId="d1" onClose={jest.fn()} onBooked={onBooked} />);
  return { onBooked };
}

async function pickPatient() {
  await userEvent.type(screen.getByPlaceholderText('Search by name or mobile'), 'Asha');
  await userEvent.click(await screen.findByTestId('pick-patient-p1'));
  expect(screen.getByTestId('selected-patient')).toHaveTextContent('Asha Menon');
}

describe('BookAppointmentModal', () => {
  beforeEach(() => jest.clearAllMocks());

  it('books the chosen free slot for the chosen patient', async () => {
    const { onBooked } = setup();
    await pickPatient();

    expect(await screen.findByTestId('slot-09:00')).toBeDisabled();   // already taken
    await userEvent.click(screen.getByTestId('slot-09:30'));
    await userEvent.click(screen.getByTestId('submit-appointment-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('emr/appointments', expect.objectContaining({
      patient_id: 'p1', doctor_user_id: 'd1', start_time: '09:30',
    })));
    expect(onBooked).toHaveBeenCalled();
  });

  it('cannot submit until a patient and a slot are chosen', async () => {
    setup();
    expect(screen.getByTestId('submit-appointment-btn')).toBeDisabled();
    await pickPatient();
    expect(screen.getByTestId('submit-appointment-btn')).toBeDisabled();   // still no slot
  });

  it('issues a walk-in token for today without a start time', async () => {
    setup();
    await pickPatient();
    await userEvent.click(screen.getByText('Walk-in (today)'));
    await userEvent.click(screen.getByTestId('submit-appointment-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const body = (api.post as jest.Mock).mock.calls[0][1];
    expect(body.start_time).toBeUndefined();
    expect(body.patient_id).toBe('p1');
  });
});
