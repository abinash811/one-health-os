import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import InvoicePrint from '../pages/InvoicePrint';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

const INVOICE = {
  id: 'inv1', patient_id: 'p1', patient_name: 'Asha Menon', patient_uhid: 'SUN-000001', invoice_number: 'INV-000012',
  counter: 'front_desk', status: 'paid', gross_paise: 50000, discount_paise: 5000, net_paise: 45000, paid_paise: 45000,
  balance_paise: 0, cancel_reason: null, created_at: '2026-10-02T09:00:00Z',
  lines: [{ charge_id: 'c1', description: 'Consultation — Dr Rao', quantity: 1, unit_price_paise: 50000, total_paise: 50000,
    source_module: 'emr', source_ref: 'a1' }],
  payments: [{ id: 'pay1', patient_id: 'p1', invoice_id: 'inv1', invoice_number: 'INV-000012', amount_paise: 45000,
    mode: 'upi', reference: 'ab12', receipt_number: 'RCT-000042', paid_on: '2026-10-02', created_at: null }],
};
const SETTINGS = { clinic_name: 'Sunrise Family Clinic', clinic_address: null, clinic_phone: null, registration_no: 'KMC-1',
  rx_footer: 'Closed Sundays', fallback: { clinic_name: 'Sunrise Pharmacy', clinic_address: '12 MG Road', clinic_phone: '9876543210' } };

function mockApi(invoice: unknown = INVOICE, settings: unknown = SETTINGS) {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('emr/settings')) return settings ? Promise.resolve({ data: settings }) : Promise.reject(new Error('403'));
    return Promise.resolve({ data: invoice });
  });
}
const renderPage = () => render(
  <MemoryRouter initialEntries={['/patient-billing/invoices/inv1/print']}>
    <Routes><Route path="/patient-billing/invoices/:id/print" element={<InvoicePrint />} /></Routes>
  </MemoryRouter>,
);

describe('InvoicePrint', () => {
  beforeEach(() => jest.clearAllMocks());

  it('prints clinic, patient, lines, totals and receipts on one sheet', async () => {
    mockApi();
    renderPage();
    expect(await screen.findByTestId('invoice-clinic-name')).toHaveTextContent('Sunrise Family Clinic');
    expect(screen.getByTestId('invoice-number')).toHaveTextContent('INV-000012');
    expect(screen.getByTestId('invoice-patient')).toHaveTextContent('Asha Menon');
    expect(screen.getByTestId('invoice-lines')).toHaveTextContent('Consultation — Dr Rao');
    const totals = screen.getByTestId('invoice-totals');
    expect(totals).toHaveTextContent('Gross₹500');
    expect(totals).toHaveTextContent('− ₹50');
    expect(totals).toHaveTextContent('Paid₹450');
    expect(totals).toHaveTextContent('Balance₹0');
    expect(screen.getByTestId('invoice-receipts')).toHaveTextContent('RCT-000042');
    expect(screen.getByTestId('invoice-receipts')).toHaveTextContent('UPI · ab12');
    expect(screen.getByTestId('invoice-footer')).toHaveTextContent('Closed Sundays');
  });

  it('still prints the invoice, without a letterhead, when clinic settings cannot be read', async () => {
    mockApi(INVOICE, null);
    renderPage();
    expect(await screen.findByTestId('invoice-number')).toBeInTheDocument();
    expect(screen.queryByTestId('invoice-clinic-name')).not.toBeInTheDocument();
  });

  it('marks a cancelled invoice', async () => {
    mockApi({ ...INVOICE, status: 'cancelled', payments: [] });
    renderPage();
    expect(await screen.findByTestId('invoice-cancelled')).toBeInTheDocument();
  });

  it('opens the browser print dialog', async () => {
    mockApi();
    window.print = jest.fn();
    renderPage();
    await userEvent.click(await screen.findByTestId('print-btn'));
    expect(window.print).toHaveBeenCalled();
  });

  it('shows the server reason when the invoice cannot be loaded', async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error('Invoice not found'));
    renderPage();
    expect(await screen.findByText('Invoice not found')).toBeInTheDocument();
  });
});
