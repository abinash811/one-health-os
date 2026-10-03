import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Consultation from '../pages/Consultation';
import PrescriptionPrint from '../pages/PrescriptionPrint';
import api from '@/lib/axios';

// EMR step 2 (docs/28_EMR_SCOPE.md): ONE prescription per visit — consultation
// record + medicines — edited on the doctor's screen and printed on A4.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const RX = {
  id: 'rx1', rx_number: 'RX-000001', status: 'draft', appointment_id: 'a1', patient_id: 'p1',
  patient_name: 'Asha Menon', doctor_id: 'd1', doctor_name: 'Dr Rao', vitals: { pulse: 72 },
  complaints: 'Fever', diagnosis: null, advice: null, follow_up_date: null, issued_at: null,
  cancel_reason: null, created_at: '2026-10-05T09:00:00Z', items: [],
  patient: { gender: 'female', phone: '9000000001', age: 41, allergies: 'Penicillin', date_of_birth: null },
  clinic: { name: 'Sunrise Clinic', address: '1 MG Road', phone: '9999999999', email: null, registration_no: null, footer: null },
  doctor: { specialty: null, qualification: null, registration_no: null }, patient_uhid: 'UH-000001',
};

const NOT_FOUND = Object.assign(new Error('No prescription for this visit yet'), { response: { status: 404 } });

function mockApi(rx = RX, history: unknown[] = [], existing = false) {
  (api.post as jest.Mock).mockImplementation((url: string) => Promise.resolve({
    data: url.endsWith('/issue') ? { ...rx, status: 'issued' } : rx }));
  (api.put as jest.Mock).mockImplementation((_u: string, body: Record<string, unknown>) =>
    Promise.resolve({ data: { ...rx, ...body, items: body.items } }));
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('emr/appointments/')) return existing ? Promise.resolve({ data: rx }) : Promise.reject(NOT_FOUND);
    if (url.includes('suggestions')) return Promise.resolve({ data: ['Paracetamol 650', 'Pantoprazole 40'] });
    if (url.includes('/prescriptions') && url.includes('patients')) return Promise.resolve({ data: history });
    return Promise.resolve({ data: rx });
  });
}

const renderConsult = () => render(
  <MemoryRouter initialEntries={['/emr/consult/a1']}>
    <Routes>
      <Route path="/emr/consult/:appointmentId" element={<Consultation />} />
      <Route path="/emr/prescriptions/:id/print" element={<div data-testid="print-route" />} />
    </Routes>
  </MemoryRouter>,
);

describe('Consultation', () => {
  beforeEach(() => jest.clearAllMocks());

  it('opens the visit prescription and shows patient, allergy warning and prior visits', async () => {
    mockApi(RX, [{ ...RX, id: 'old', rx_number: 'RX-000000', status: 'issued', diagnosis: 'Migraine',
      issued_at: '2026-09-01T09:00:00Z', items: [{ medicine_name: 'Sumatriptan' }] }]);
    renderConsult();

    expect(await screen.findByTestId('consult-patient')).toHaveTextContent('Asha Menon');
    expect(api.get).toHaveBeenCalledWith('emr/appointments/a1/prescription');          // read first…
    expect(api.post).toHaveBeenCalledWith('emr/prescriptions', { appointment_id: 'a1' });   // …start only when there is none
    expect(screen.getByTestId('allergy-banner')).toHaveTextContent('Penicillin');
    expect(screen.getByTestId('vital-pulse')).toHaveValue(72);
    expect(await screen.findByText('Migraine')).toBeInTheDocument();
  });

  it('saves everything as one record, dropping blank medicine rows', async () => {
    mockApi();
    renderConsult();
    await screen.findByTestId('consult-patient');

    await userEvent.type(screen.getByTestId('rx-diagnosis'), 'Viral fever');
    await userEvent.type(screen.getByTestId('rx-name-0'), 'Paracetamol 650');
    await userEvent.type(screen.getByTestId('rx-freq-0'), 'TDS');
    await userEvent.click(screen.getByTestId('add-medicine-btn')); // stays blank → dropped
    await userEvent.click(screen.getByTestId('save-draft-btn'));

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = (api.put as jest.Mock).mock.calls[0];
    expect(url).toBe('emr/prescriptions/rx1');
    expect(body.diagnosis).toBe('Viral fever');
    expect(body.vitals).toEqual({ pulse: 72 });
    expect(body.items).toEqual([expect.objectContaining({ medicine_name: 'Paracetamol 650', frequency: 'TDS' })]);
  });

  it('suggests medicines from the clinic history and fills the field on pick', async () => {
    mockApi();
    renderConsult();
    await screen.findByTestId('consult-patient');

    await userEvent.type(screen.getByTestId('rx-name-0'), 'para');
    await userEvent.click(await screen.findByText('Paracetamol 650'));
    expect(screen.getByTestId('rx-name-0')).toHaveValue('Paracetamol 650');
  });

  it('issue & print saves, issues, then goes to the print page', async () => {
    mockApi();
    renderConsult();
    await screen.findByTestId('consult-patient');
    await userEvent.type(screen.getByTestId('rx-name-0'), 'ORS');
    await userEvent.click(screen.getByTestId('issue-rx-btn'));

    await waitFor(() => expect(screen.getByTestId('print-route')).toBeInTheDocument());
    expect(api.post).toHaveBeenCalledWith('emr/prescriptions/rx1/issue');
  });

  it('an issued prescription is read-only with a Print action', async () => {
    mockApi({ ...RX, status: 'issued' });
    renderConsult();
    await screen.findByTestId('consult-patient');
    expect(screen.getByTestId('rx-diagnosis')).toBeDisabled();
    expect(screen.queryByTestId('issue-rx-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('print-rx-btn')).toBeInTheDocument();
  });

  it('opens an existing prescription without trying to start one (so view-only roles can read it)', async () => {
    mockApi({ ...RX, status: 'issued' }, [], true);
    renderConsult();
    expect(await screen.findByTestId('consult-patient')).toHaveTextContent('Asha Menon');
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.getByTestId('rx-diagnosis')).toBeDisabled();
  });

  it('shows the real server reason when the prescription cannot be opened', async () => {
    (api.get as jest.Mock).mockRejectedValue(NOT_FOUND);
    (api.post as jest.Mock).mockRejectedValue(new Error("Your role does not have the 'prescriptions:create' permission"));
    renderConsult();
    expect(await screen.findByText(/prescriptions:create/)).toBeInTheDocument();
  });
});

describe('PrescriptionPrint', () => {
  beforeEach(() => jest.clearAllMocks());

  const renderPrint = () => render(
    <MemoryRouter initialEntries={['/emr/prescriptions/rx1/print']}>
      <Routes><Route path="/emr/prescriptions/:id/print" element={<PrescriptionPrint />} /></Routes>
    </MemoryRouter>,
  );

  it('prints clinic, patient, medicines and doctor on one sheet', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: {
      ...RX, status: 'issued', diagnosis: 'Viral fever', vitals: { bp_systolic: 120, bp_diastolic: 80, pulse: 72 },
      items: [{ id: 'i1', medicine_name: 'Paracetamol 650', dosage: '1 tab', frequency: 'TDS', duration_days: 3,
        instructions: 'After food', quantity: 9 }],
    } });
    renderPrint();

    expect(await screen.findByTestId('rx-clinic-name')).toHaveTextContent('Sunrise Clinic');
    expect(screen.getByTestId('rx-patient-name')).toHaveTextContent('Asha Menon');
    expect(screen.getByText('Paracetamol 650')).toBeInTheDocument();
    expect(screen.getByText('After food')).toBeInTheDocument();
    expect(screen.getByText(/BP 120\/80 mmHg/)).toBeInTheDocument();
    expect(screen.getByText('Dr Rao')).toBeInTheDocument();
    expect(screen.queryByTestId('rx-not-valid')).not.toBeInTheDocument();
  });

  it('prints the clinic registration, doctor credentials and footer from settings', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: { ...RX, status: 'issued',
      clinic: { ...RX.clinic, registration_no: 'KMC-123', footer: 'Closed Sundays' },
      doctor: { specialty: 'Paediatrics', qualification: 'MBBS, MD', registration_no: 'KMC-9981' } } });
    renderPrint();
    expect(await screen.findByTestId('rx-clinic-reg')).toHaveTextContent('KMC-123');
    expect(screen.getByTestId('rx-doctor-quals')).toHaveTextContent('MBBS, MD · Paediatrics');
    expect(screen.getByText('Reg. no. KMC-9981')).toBeInTheDocument();
    expect(screen.getByTestId('rx-footer')).toHaveTextContent('Closed Sundays');
  });

  it('marks a draft sheet as not issued', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: RX });
    renderPrint();
    expect(await screen.findByTestId('rx-not-valid')).toHaveTextContent('Draft');
  });

  it('opens the browser print dialog from the Print button', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: { ...RX, status: 'issued' } });
    window.print = jest.fn();
    renderPrint();
    await userEvent.click(await screen.findByTestId('print-btn'));
    expect(window.print).toHaveBeenCalled();
  });
});
