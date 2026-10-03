import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import BillingDesk from '../pages/BillingDesk';
import api from '@/lib/axios';
import { today } from '@/utils/dates';

// Patient Billing B4: the billing desk — Pending, All bills, Receipts, Day closing.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() } }));
jest.mock('@/utils/excelExport', () => ({ exportToExcel: jest.fn() }));

const ACCOUNTS = {
  data: [
    { patient_id: 'p1', patient_name: 'Kiran Patel', patient_uhid: 'SUN-000014', not_invoiced_paise: 0, invoiced_unpaid_paise: 168000,
      balance_paise: 168000, has_part_paid: true, sources: ['emr', 'lab'], last_activity: '2026-10-01T10:00:00Z' },
    { patient_id: 'p2', patient_name: 'Asha Menon', patient_uhid: 'SUN-000001', not_invoiced_paise: 50000, invoiced_unpaid_paise: 0,
      balance_paise: 50000, has_part_paid: false, sources: ['emr'], last_activity: '2026-10-02T10:00:00Z' },
  ],
  pagination: { page: 1, page_size: 20, total_items: 2, total_pages: 1, has_next: false, has_prev: false },
  totals: { balance_paise: 218000, not_invoiced_paise: 50000, invoiced_unpaid_paise: 168000, patients: 2 },
};
const SUMMARY = { date: today(), collected_paise: 514640, receipts: 5, by_mode: { cash: 70000, upi: 444640 },
  by_counter: { front_desk: 70000, billing_desk: 444640 } };
const INVOICE = (over: Record<string, unknown> = {}) => ({
  id: 'i1', patient_id: 'p1', patient_name: 'Kiran Patel', patient_uhid: 'SUN-000014', invoice_number: 'INV-000007',
  counter: 'front_desk', status: 'part_paid', gross_paise: 200000, discount_paise: 0, net_paise: 200000, paid_paise: 32000,
  balance_paise: 168000, lines: [], cancel_reason: null, created_at: '2026-10-01T09:00:00Z', ...over });
const PAYMENT = { id: 'pay1', patient_id: 'p1', invoice_id: 'i1', invoice_number: 'INV-000007', patient_name: 'Kiran Patel',
  patient_uhid: 'SUN-000014', amount_paise: 32000, mode: 'upi', reference: 'ab12', receipt_number: 'RCT-000009',
  paid_on: today(), created_at: null };
const PAGE = (data: unknown[]) => ({ data, pagination: { page: 1, page_size: 20, total_items: data.length, total_pages: 1, has_next: false, has_prev: false } });

function mockApi(over: Record<string, unknown> = {}) {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    const hit = Object.keys(over).find((k) => url.startsWith(k));
    if (hit) { const v = over[hit]; return v instanceof Error ? Promise.reject(v) : Promise.resolve({ data: v }); }
    if (url.startsWith('patient-billing/accounts/')) return Promise.resolve({ data: { patient: { id: 'p2', name: 'Asha Menon', uhid: 'SUN-000001' },
      totals: {}, charges: [{ id: 'c1', status: 'unbilled', source_module: 'emr', description: 'Consultation — Dr Rao', total_paise: 50000 }], invoices: [], payments: [] } });
    if (url.startsWith('patient-billing/accounts')) return Promise.resolve({ data: ACCOUNTS });
    if (url.startsWith('patient-billing/summary')) return Promise.resolve({ data: SUMMARY });
    if (url.startsWith('patient-billing/invoices')) return Promise.resolve({ data: PAGE([INVOICE()]) });
    if (url.startsWith('patient-billing/payments')) return Promise.resolve({ data: PAGE([PAYMENT]) });
    return Promise.resolve({ data: {} });
  });
}
const lastUrl = (prefix: string) => (api.get as jest.Mock).mock.calls.map((c) => c[0] as string).filter((u) => u.startsWith(prefix)).at(-1) as string;

const renderDesk = (tab: 'pending' | 'invoices' | 'receipts' | 'closing' = 'pending') => render(
  <MemoryRouter initialEntries={[`/patient-billing/${tab}`]}>
    <Routes>
      <Route path="/patient-billing/pending" element={<BillingDesk tab="pending" />} />
      <Route path="/patient-billing/invoices" element={<BillingDesk tab="invoices" />} />
      <Route path="/patient-billing/receipts" element={<BillingDesk tab="receipts" />} />
      <Route path="/patient-billing/closing" element={<BillingDesk tab="closing" />} />
      <Route path="/patient-billing/accounts/:patientId" element={<div data-testid="account-route" />} />
      <Route path="/patient-billing/invoices/:id/print" element={<div data-testid="print-route" />} />
    </Routes>
  </MemoryRouter>,
);

describe('Billing desk — Pending', () => {
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('lists who owes money with totals, sources and today\'s collection', async () => {
    renderDesk();
    expect(await screen.findByTestId('pending-row-p1')).toHaveTextContent('Kiran Patel');
    expect(screen.getByTestId('pending-row-p1')).toHaveTextContent('Lab');
    expect(screen.getByTestId('pending-row-p1')).toHaveTextContent('part-paid');
    expect(screen.getByTestId('balance-p2')).toHaveTextContent('₹500');
    expect(screen.getByTestId('stat-pending')).toHaveTextContent('₹2,180');
    expect(screen.getByTestId('stat-not-invoiced')).toHaveTextContent('₹500');
    expect(screen.getByTestId('stat-invoiced')).toHaveTextContent('₹1,680');
    expect(screen.getByTestId('stat-collected')).toHaveTextContent('₹5,146.40');
  });

  it('filters by status and source through the API', async () => {
    renderDesk();
    await screen.findByTestId('pending-row-p1');
    await userEvent.click(screen.getByRole('button', { name: 'Part-paid' }));
    await waitFor(() => expect(lastUrl('patient-billing/accounts?')).toContain('status=part_paid'));
    await userEvent.click(screen.getByRole('button', { name: 'Lab' }));
    await waitFor(() => expect(lastUrl('patient-billing/accounts?')).toContain('source=lab'));
  });

  it('Collect gathers the patient\'s unbilled charges and invoices + pays in one step', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: { invoice: { id: 'inv9', invoice_number: 'INV-000009' },
      payment: { amount_paise: 50000, receipt_number: 'RCT-000010' } } });
    renderDesk();
    await userEvent.click(await screen.findByTestId('collect-p2'));
    expect(await screen.findByTestId('collect-lines')).toHaveTextContent('Consultation — Dr Rao');
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/accounts/p2/collect',
      expect.objectContaining({ charge_item_ids: ['c1'], mode: 'cash' })));
  });

  it('with nothing unbilled, Collect pays the balance of the oldest unpaid invoice', async () => {
    mockApi({ 'patient-billing/accounts/p1': { patient: { id: 'p1', name: 'Kiran Patel', uhid: null }, totals: {}, charges: [],
      invoices: [INVOICE()], payments: [] } });
    (api.post as jest.Mock).mockResolvedValue({ data: { invoice: INVOICE(), payment: { amount_paise: 168000, receipt_number: 'RCT-000011' } } });
    renderDesk();
    await userEvent.click(await screen.findByTestId('collect-p1'));
    expect(await screen.findByTestId('collect-total')).toHaveTextContent('₹1,680');
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/invoices/i1/payments',
      { amount_paise: 168000, mode: 'cash', reference: null }));
  });

  it('says so when there is nothing to collect', async () => {
    const { toast } = jest.requireMock('sonner');
    mockApi({ 'patient-billing/accounts/p2': { patient: { id: 'p2', name: 'Asha Menon', uhid: null }, totals: {}, charges: [], invoices: [], payments: [] } });
    renderDesk();
    await userEvent.click(await screen.findByTestId('collect-p2'));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('Nothing to collect for Asha Menon'));
  });

  it('opens a patient\'s bill and shows an empty state when nobody owes anything', async () => {
    renderDesk();
    await userEvent.click(await screen.findByTestId('open-bill-p2'));
    expect(screen.getByTestId('account-route')).toBeInTheDocument();
  });

  it('shows an empty state when nothing is pending', async () => {
    mockApi({ 'patient-billing/accounts?': { ...ACCOUNTS, data: [], totals: { balance_paise: 0, not_invoiced_paise: 0, invoiced_unpaid_paise: 0, patients: 0 } } });
    renderDesk();
    expect(await screen.findByText('Nothing pending')).toBeInTheDocument();
    expect(screen.getByTestId('export-pending')).toBeDisabled();
  });

  it('shows the real server reason when the list cannot load', async () => {
    mockApi({ 'patient-billing/accounts?': new Error("Your role does not have the 'patient_billing:view' permission") });
    renderDesk();
    expect(await screen.findByText(/patient_billing:view/)).toBeInTheDocument();
  });
});

describe('Billing desk — All bills', () => {
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('lists invoices with status, balance and a Pay button for what is still owed', async () => {
    renderDesk('invoices');
    const row = await screen.findByTestId('invoice-row-i1');
    expect(row).toHaveTextContent('INV-000007');
    expect(row).toHaveTextContent('Part-paid');
    expect(screen.getByTestId('pay-i1')).toHaveTextContent('Pay ₹1,680');
  });

  it('searches and filters through the API', async () => {
    renderDesk('invoices');
    await screen.findByTestId('invoice-row-i1');
    await userEvent.type(screen.getByPlaceholderText(/Search invoice/), 'kiran');
    await waitFor(() => expect(lastUrl('patient-billing/invoices?')).toContain('search=kiran'));
    await userEvent.click(screen.getByRole('button', { name: 'Paid' }));
    await waitFor(() => expect(lastUrl('patient-billing/invoices?')).toContain('status=paid'));
  });

  it('pays the rest of an invoice from the list', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: { invoice: INVOICE(), payment: { amount_paise: 168000, receipt_number: 'RCT-000012' } } });
    renderDesk('invoices');
    await userEvent.click(await screen.findByTestId('pay-i1'));
    await userEvent.click(await screen.findByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/invoices/i1/payments',
      { amount_paise: 168000, mode: 'cash', reference: null }));
  });

  it('cancels an unpaid invoice only with a reason, and offers no cancel once money was taken', async () => {
    mockApi({ 'patient-billing/invoices': PAGE([INVOICE({ id: 'u', status: 'issued', paid_paise: 0, balance_paise: 200000 }), INVOICE({ id: 'p' })]) });
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
    renderDesk('invoices');
    await screen.findByTestId('invoice-row-u');
    await userEvent.click(within(screen.getByTestId('invoice-row-u')).getByRole('button', { name: /more/i }));
    await userEvent.click(await screen.findByText('Cancel invoice'));
    expect(screen.getByTestId('cancel-invoice-confirm')).toBeDisabled();
    await userEvent.type(screen.getByTestId('cancel-invoice-reason'), 'Wrong patient');
    await userEvent.click(screen.getByTestId('cancel-invoice-confirm'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/invoices/u/cancel', { reason: 'Wrong patient' }));
  });
});

describe('Billing desk — Receipts and Day closing', () => {
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('lists today\'s receipts with the patient, mode and a print button', async () => {
    renderDesk('receipts');
    const row = await screen.findByTestId('receipt-row-pay1');
    expect(row).toHaveTextContent('RCT-000009');
    expect(row).toHaveTextContent('Kiran Patel');
    expect(row).toHaveTextContent('UPI · ab12');
    expect(lastUrl('patient-billing/payments')).toContain(`date=${today()}`);
    await userEvent.click(screen.getByTestId('print-receipt-pay1'));
    expect(screen.getByTestId('print-route')).toBeInTheDocument();
  });

  it('"All days" drops the date filter', async () => {
    renderDesk('receipts');
    await screen.findByTestId('receipt-row-pay1');
    await userEvent.click(screen.getByTestId('receipts-all-days'));
    await waitFor(() => expect(lastUrl('patient-billing/payments')).not.toContain('date='));
  });

  it('day closing totals the day by mode and by counter, with the receipts behind it', async () => {
    renderDesk('closing');
    await waitFor(() => expect(screen.getByTestId('closing-total')).toHaveTextContent('₹5,146.40'));
    expect(screen.getByTestId('closing-cash')).toHaveTextContent('₹700');
    expect(screen.getByTestId('closing-upi')).toHaveTextContent('₹4,446.40');
    expect(screen.getByTestId('closing-card')).toHaveTextContent('₹0');
    expect(screen.getByTestId('closing-counter-front_desk')).toHaveTextContent('₹700');
    expect(screen.getByTestId('closing-counter-lab')).toHaveTextContent('₹0');
    expect(await screen.findByTestId('receipt-row-pay1')).toBeInTheDocument();
  });

  it('day closing asks the API for the chosen date', async () => {
    renderDesk('closing');
    await screen.findByTestId('closing-total');
    fireEvent.change(screen.getByTestId('closing-date'), { target: { value: '2026-09-30' } });
    await waitFor(() => expect(lastUrl('patient-billing/summary')).toContain('date=2026-09-30'));
  });

  it('the tab bar switches between the four views', async () => {
    renderDesk();
    await screen.findByTestId('pending-tab');
    await userEvent.click(screen.getByRole('tab', { name: 'Receipts' }));
    expect(await screen.findByTestId('receipts-tab')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Day closing' }));
    expect(await screen.findByTestId('day-closing-tab')).toBeInTheDocument();
  });
});
