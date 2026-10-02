import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Appointments from '../pages/Appointments';
import CancelAppointmentDialog from '../components/CancelAppointmentDialog';
import { AuthContext } from '@/App';
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

const SUMMARY = { date: '2026-10-05', collected_paise: 450000, receipts: 9, by_mode: {}, by_counter: {} };

function mockApi(rows: unknown[], summary: unknown = null) {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('patient-billing/summary')) return summary ? Promise.resolve({ data: summary }) : Promise.reject(new Error('403'));
    return Promise.resolve({ data: url.startsWith('emr/doctors') ? DOCTORS : rows });
  });
}

const renderPage = (role = 'receptionist') => render(
  <AuthContext.Provider value={{ user: { role } } as never}>
    <MemoryRouter><Appointments /></MemoryRouter>
  </AuthContext.Provider>,
);

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
    expect(screen.getByTestId('queue-rx-c')).toHaveTextContent('Write Rx');
    expect(screen.getByTestId('queue-rx-d')).toHaveTextContent('View Rx');
    expect(screen.queryByTestId('queue-rx-w')).not.toBeInTheDocument();
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

  describe('consultation fee (Patient Billing)', () => {
    const fee = (over: Record<string, unknown> = {}) => ({
      charge_id: 'c1', amount_paise: 50000, status: 'unpaid', paid_paise: 0, balance_paise: 50000, mode: null,
      invoice_id: null, invoice_number: null, ...over });

    it('shows each visit\'s fee state next to its status', async () => {
      mockApi([
        row({ id: 'u', status: 'checked_in', fee: fee() }),
        row({ id: 'p', status: 'in_consult', fee: fee({ status: 'part_paid', paid_paise: 20000, balance_paise: 30000, invoice_id: 'i1', invoice_number: 'INV-000001', mode: 'upi' }) }),
        row({ id: 'd', status: 'completed', fee: fee({ status: 'paid', balance_paise: 0, paid_paise: 50000, mode: 'upi', invoice_id: 'i2' }) }),
        row({ id: 'n', status: 'booked', fee: null }),
      ]);
      renderPage();
      await screen.findByTestId('queue-row-u');
      expect(screen.getByTestId('queue-row-u')).toHaveTextContent('₹500 · Unpaid');
      expect(screen.getByTestId('queue-row-p')).toHaveTextContent('₹500 · Part-paid');
      expect(screen.getByTestId('queue-row-d')).toHaveTextContent('₹500 · Paid (UPI)');
      expect(screen.getByTestId('fee-none')).toBeInTheDocument();
    });

    it('Collect shows the balance still owed and opens the collect dialog for the visit\'s fee', async () => {
      mockApi([row({ id: 'u', status: 'checked_in', fee: fee() })]);
      renderPage();
      const btn = await screen.findByTestId('queue-collect-u');
      expect(btn).toHaveTextContent('Collect ₹500');
      await userEvent.click(btn);
      expect(await screen.findByTestId('collect-lines')).toHaveTextContent('Consultation — Dr Rao');
    });

    it('a part-paid visit collects the rest of its existing invoice', async () => {
      mockApi([row({ id: 'p', status: 'in_consult', fee: fee({ status: 'part_paid', paid_paise: 20000,
        balance_paise: 30000, invoice_id: 'i1', invoice_number: 'INV-000001' }) })]);
      (api.post as jest.Mock).mockResolvedValue({ data: { invoice: { id: 'i1', invoice_number: 'INV-000001' },
        payment: { amount_paise: 30000, receipt_number: 'RCT-000002' } } });
      renderPage();
      const btn = await screen.findByTestId('queue-collect-p');
      expect(btn).toHaveTextContent('Collect ₹300');
      await userEvent.click(btn);
      await userEvent.click(await screen.findByTestId('collect-submit-btn'));
      await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/invoices/i1/payments',
        { amount_paise: 30000, mode: 'cash', reference: null }));
    });

    it('no Collect button once paid, for cancelled visits, or for a doctor', async () => {
      mockApi([row({ id: 'd', status: 'completed', fee: fee({ status: 'paid', balance_paise: 0, invoice_id: 'i2' }) }),
        row({ id: 'x', status: 'cancelled', fee: fee() })]);
      renderPage();
      await screen.findByTestId('queue-row-d');
      expect(screen.queryByTestId('queue-collect-d')).not.toBeInTheDocument();
      expect(screen.queryByTestId('queue-collect-x')).not.toBeInTheDocument();
    });

    it('doctors see the fee but are not offered Collect', async () => {
      mockApi([row({ id: 'u', status: 'checked_in', fee: fee() })]);
      renderPage('doctor');
      await screen.findByTestId('queue-row-u');
      expect(screen.getByTestId('queue-row-u')).toHaveTextContent('₹500 · Unpaid');
      expect(screen.queryByTestId('queue-collect-u')).not.toBeInTheDocument();
    });

    it('summarises the day, including money collected today', async () => {
      mockApi([row({ id: 'w', status: 'checked_in' }), row({ id: 'c', status: 'in_consult' }),
        row({ id: 'd', status: 'completed' })], SUMMARY);
      renderPage();
      expect(await screen.findByTestId('stat-collected')).toHaveTextContent('₹4,500');
      expect(screen.getByTestId('stat-waiting')).toHaveTextContent('1');
      expect(screen.getByTestId('stat-in-consult')).toHaveTextContent('1');
      expect(screen.getByTestId('stat-done')).toHaveTextContent('1');
      expect(screen.getByTestId('queue-summary')).toHaveTextContent('9 receipts');
    });

    it('hides the collected card when billing is not visible to this user', async () => {
      mockApi([row({})], null);
      renderPage();
      await screen.findByTestId('queue-row-a1');
      expect(screen.getByTestId('stat-waiting')).toBeInTheDocument();
      expect(screen.queryByTestId('stat-collected')).not.toBeInTheDocument();
    });
  });
});
