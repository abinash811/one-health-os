import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AccountBill from '../components/AccountBill';
import api from '@/lib/axios';

// Patient Billing B4: one patient's complete bill (billing desk page and the profile's Billing tab).

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() } }));

const charge = (id: string, over: Record<string, unknown> = {}) => ({ id, patient_id: 'p1', patient_name: 'Asha Menon', patient_uhid: 'SUN-000001',
  source_module: 'emr', source_ref: null, description: 'Consultation — Dr Rao', quantity: 1, unit_price_paise: 50000, total_paise: 50000,
  status: 'unbilled', invoice_id: null, void_reason: null, created_at: '2026-10-02T09:00:00Z', ...over });
const ACCOUNT = {
  patient: { id: 'p1', name: 'Asha Menon', uhid: 'SUN-000001' },
  totals: { total_charges_paise: 140000, paid_paise: 50000, not_invoiced_paise: 40000, invoiced_unpaid_paise: 0, balance_paise: 40000 },
  charges: [charge('c1', { status: 'paid' }), charge('c2', { description: 'Dressing', total_paise: 4000, status: 'unbilled' }),
    charge('c3', { description: 'Entered twice', status: 'void', void_reason: 'dup' })],
  invoices: [{ id: 'i1', patient_id: 'p1', patient_name: 'Asha Menon', patient_uhid: null, invoice_number: 'INV-000001', counter: 'front_desk',
    status: 'paid', gross_paise: 50000, discount_paise: 0, net_paise: 50000, paid_paise: 50000, balance_paise: 0, lines: [],
    cancel_reason: null, created_at: '2026-10-02T09:30:00Z' }],
  payments: [{ id: 'pay1', patient_id: 'p1', invoice_id: 'i1', invoice_number: 'INV-000001', amount_paise: 50000, mode: 'upi',
    reference: 'ab12', receipt_number: 'RCT-000001', paid_on: '2026-10-02', created_at: null }],
};

const renderBill = (props: Record<string, unknown> = {}) => render(
  <MemoryRouter initialEntries={['/x']}>
    <Routes>
      <Route path="/x" element={<AccountBill patientId="p1" {...props} />} />
      <Route path="/patient-billing/invoices/:id/print" element={<div data-testid="print-route" />} />
    </Routes>
  </MemoryRouter>,
);

describe('AccountBill', () => {
  beforeEach(() => { jest.clearAllMocks(); (api.get as jest.Mock).mockResolvedValue({ data: ACCOUNT }); });

  it('shows the patient, the totals and every charge with where it came from and its status', async () => {
    renderBill();
    expect(await screen.findByTestId('account-patient')).toHaveTextContent('Asha Menon');
    expect(screen.getByTestId('total-charges')).toHaveTextContent('₹1,400');
    expect(screen.getByTestId('total-paid')).toHaveTextContent('₹500');
    expect(screen.getByTestId('total-balance')).toHaveTextContent('₹400');
    expect(screen.getByTestId('charge-row-c2')).toHaveTextContent('Dressing');
    expect(screen.getByTestId('charge-row-c2')).toHaveTextContent('Unbilled');
    expect(screen.getByTestId('charge-row-c1')).toHaveTextContent('Paid');
    expect(screen.getByTestId('charge-row-c3').className).toContain('line-through');   // voided charges stay visible, struck through
    expect(screen.getByTestId('account-payments')).toHaveTextContent('UPI · ab12');
    expect(screen.getByTestId('account-invoice-i1')).toHaveTextContent('INV-000001');
  });

  it('hides the patient header when embedded in the profile', async () => {
    renderBill({ showPatient: false });
    await screen.findByTestId('account-totals');
    expect(screen.queryByTestId('account-patient')).not.toBeInTheDocument();
  });

  it('Collect offers what is owed and collects the unbilled charges', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: ACCOUNT });
    (api.post as jest.Mock).mockResolvedValue({ data: { invoice: { id: 'i2', invoice_number: 'INV-000002' },
      payment: { amount_paise: 4000, receipt_number: 'RCT-000002' } } });
    renderBill();
    const btn = await screen.findByTestId('account-collect');
    expect(btn).toHaveTextContent('Collect ₹400');
    await userEvent.click(btn);
    expect(await screen.findByTestId('collect-lines')).toHaveTextContent('Dressing');
    expect(screen.getByTestId('collect-lines')).not.toHaveTextContent('Entered twice');   // void charges are never collected
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/accounts/p1/collect',
      expect.objectContaining({ charge_item_ids: ['c2'] })));
  });

  it('no Collect button once everything is paid', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: { ...ACCOUNT,
      totals: { ...ACCOUNT.totals, not_invoiced_paise: 0, balance_paise: 0 }, charges: [charge('c1', { status: 'paid' })] } });
    renderBill();
    await screen.findByTestId('account-totals');
    expect(screen.queryByTestId('account-collect')).not.toBeInTheDocument();
  });

  it('a patient with no charges yet gets a friendly empty state, not an error', async () => {
    (api.get as jest.Mock).mockRejectedValue(Object.assign(new Error('No billing account for this patient yet'), { response: { status: 404 } }));
    renderBill();
    expect(await screen.findByText('No charges yet')).toBeInTheDocument();
  });

  it('any other failure shows its real reason', async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error("Your role does not have the 'patient_billing:view' permission"));
    renderBill();
    expect(await screen.findByText(/patient_billing:view/)).toBeInTheDocument();
  });
});
