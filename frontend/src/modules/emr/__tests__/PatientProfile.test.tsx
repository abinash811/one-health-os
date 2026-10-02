import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PatientProfile from '../pages/PatientProfile';
import api from '@/lib/axios';

// EMR patient profile: details + allergy warning + every visit with its Rx.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const PATIENT = { id: 'p1', name: 'Asha Menon', phone: '9000012345', age: 41, gender: 'female', allergies: 'Penicillin',
  blood_group: 'B+', city: 'Pune', email: null, address: null, notes: null, alternate_phone: null,
  date_of_birth: null, source: 'emr', customer_id: null, is_active: true };
const appt = (id: string, over = {}) => ({ id, patient_id: 'p1', patient_name: 'Asha Menon', doctor_user_id: 'd1',
  doctor_name: 'Dr Rao', appointment_date: '2026-09-20', start_time: '10:00', end_time: '10:30', token_number: 1,
  appointment_type: 'scheduled', status: 'completed', reason: 'Fever', cancel_reason: null, ...over });
const rx = (id: string, apptId: string, over = {}) => ({ id, rx_number: 'RX-000001', status: 'issued', appointment_id: apptId,
  patient_id: 'p1', diagnosis: 'Viral fever', follow_up_date: null, items: [{ medicine_name: 'Paracetamol 650' }], ...over });

function mockApi({ visits = [appt('a1'), appt('a2', { status: 'cancelled', cancel_reason: 'Travelling', appointment_date: '2026-09-10' })],
  rxs = [rx('rx1', 'a1')] }: { visits?: unknown[]; rxs?: unknown[] } = {}) {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('emr/patients/p1/prescriptions')) return Promise.resolve({ data: rxs });
    if (url.startsWith('emr/patients/p1')) return Promise.resolve({ data: PATIENT });
    if (url.startsWith('emr/appointments')) return Promise.resolve({ data: visits });
    if (url.startsWith('emr/doctors')) return Promise.resolve({ data: [{ id: 'd1', name: 'Dr Rao', role: 'doctor' }] });
    return Promise.resolve({ data: [] });
  });
}

const renderPage = () => render(
  <MemoryRouter initialEntries={['/emr/patients/p1']}>
    <Routes>
      <Route path="/emr/patients/:patientId" element={<PatientProfile />} />
      <Route path="/emr/consult/:id" element={<div data-testid="consult-route" />} />
      <Route path="/emr/prescriptions/:id/print" element={<div data-testid="print-route" />} />
    </Routes>
  </MemoryRouter>,
);

describe('PatientProfile', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows details, the allergy warning and each visit with its prescription', async () => {
    mockApi();
    renderPage();

    expect(await screen.findByTestId('profile-allergies')).toHaveTextContent('Penicillin');
    expect(await screen.findByTestId('visit-a1')).toHaveTextContent('Viral fever');
    expect(screen.getByTestId('visit-a1')).toHaveTextContent('Paracetamol 650');
    expect(screen.getByTestId('visit-a2')).toHaveTextContent('Cancelled: Travelling');
    expect(screen.queryByTestId('visit-open-a2')).not.toBeInTheDocument(); // no Rx on a cancelled visit
  });

  it('opens a visit prescription and its print page', async () => {
    mockApi();
    renderPage();
    await userEvent.click(await screen.findByTestId('visit-print-a1'));
    expect(screen.getByTestId('print-route')).toBeInTheDocument();
  });

  it('opens the consultation view from a visit', async () => {
    mockApi();
    renderPage();
    await userEvent.click(await screen.findByTestId('visit-open-a1'));
    expect(screen.getByTestId('consult-route')).toBeInTheDocument();
  });

  it('shows an empty state with a booking action for a new patient', async () => {
    mockApi({ visits: [], rxs: [] });
    renderPage();
    expect(await screen.findByText('No visits yet')).toBeInTheDocument();
  });

  it('still shows visits when prescriptions are not permitted, with the real reason', async () => {
    const { toast } = jest.requireMock('sonner');
    mockApi();
    const base = (api.get as jest.Mock).getMockImplementation()!;
    (api.get as jest.Mock).mockImplementation((url: string) => url.includes('/prescriptions')
      ? Promise.reject(new Error("Your role does not have the 'prescriptions:view' permission")) : base(url));
    renderPage();

    expect(await screen.findByTestId('visit-a1')).toBeInTheDocument();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('prescriptions:view')));
  });

  it('shows the server reason when the patient cannot be loaded', async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error('Patient not found'));
    renderPage();
    expect(await screen.findByText('Patient not found')).toBeInTheDocument();
  });
});
