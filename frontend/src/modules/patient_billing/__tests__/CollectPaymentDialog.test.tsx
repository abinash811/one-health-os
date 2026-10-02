import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import CollectPaymentDialog from '../components/CollectPaymentDialog';
import api from '@/lib/axios';

// Patient Billing B3: the Collect dialog — invoice + pay in one step, part-payment, discount,
// paying the rest of an existing invoice, and real error reasons.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const CHARGES = [{ id: 'c1', description: 'Consultation — Dr Rao', total_paise: 50000 }];
const RESULT = { invoice: { id: 'inv1', invoice_number: 'INV-000001' },
  payment: { amount_paise: 50000, receipt_number: 'RCT-000001' } };

const renderDialog = (over: Record<string, unknown> = {}) => {
  const onCollected = jest.fn();
  const onClose = jest.fn();
  render(
    <MemoryRouter>
      <CollectPaymentDialog open patientId="p1" patientName="Asha Menon" charges={CHARGES}
        onClose={onClose} onCollected={onCollected} {...over} />
    </MemoryRouter>,
  );
  return { onCollected, onClose };
};

describe('CollectPaymentDialog', () => {
  beforeEach(() => { jest.clearAllMocks(); (api.post as jest.Mock).mockResolvedValue({ data: RESULT }); });

  it('shows the charges and total, and collects in full by default as cash', async () => {
    const { onCollected, onClose } = renderDialog();
    expect(screen.getByTestId('collect-lines')).toHaveTextContent('Consultation — Dr Rao');
    expect(screen.getByTestId('collect-total')).toHaveTextContent('₹500');
    expect(screen.getByTestId('collect-submit-btn')).toHaveTextContent('Collect ₹500');

    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/accounts/p1/collect', {
      charge_item_ids: ['c1'], discount_paise: 0, amount_paise: undefined, mode: 'cash', reference: null,
      counter: 'front_desk' }));
    expect(onCollected).toHaveBeenCalledWith(RESULT);
    expect(onClose).toHaveBeenCalled();
  });

  it('applies a discount to the total and sends it as paise', async () => {
    renderDialog();
    await userEvent.type(screen.getByTestId('collect-discount'), '50');
    expect(screen.getByTestId('collect-total')).toHaveTextContent('₹450');
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect((api.post as jest.Mock).mock.calls[0][1].discount_paise).toBe(5000));
  });

  it('takes a part-payment and says the rest stays as balance', async () => {
    renderDialog();
    await userEvent.type(screen.getByTestId('collect-amount'), '200');
    expect(screen.getByTestId('collect-remaining')).toHaveTextContent('₹300 will stay as balance');
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect((api.post as jest.Mock).mock.calls[0][1].amount_paise).toBe(20000));
  });

  it('refuses an amount above the total or a discount above the charges, before calling the API', async () => {
    renderDialog();
    await userEvent.type(screen.getByTestId('collect-amount'), '600');
    expect(screen.getByTestId('collect-error')).toHaveTextContent('up to ₹500');
    expect(screen.getByTestId('collect-submit-btn')).toBeDisabled();
    await userEvent.clear(screen.getByTestId('collect-amount'));
    await userEvent.type(screen.getByTestId('collect-discount'), '900');
    expect(screen.getByTestId('collect-error')).toHaveTextContent('Discount must be between');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('asks for a reference only for UPI / card and sends the chosen mode', async () => {
    renderDialog();
    expect(screen.queryByTestId('collect-ref')).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('UPI'));
    await userEvent.type(screen.getByTestId('collect-ref'), 'ab12');
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect((api.post as jest.Mock).mock.calls[0][1]).toEqual(expect.objectContaining({ mode: 'upi', reference: 'ab12' }));
  });

  it('a 100% discount issues the invoice without asking for money', async () => {
    renderDialog();
    await userEvent.type(screen.getByTestId('collect-discount'), '500');
    expect(screen.getByTestId('collect-submit-btn')).toHaveTextContent('Issue invoice');
    expect(screen.getByTestId('collect-amount')).toBeDisabled();
  });

  it('pays the rest of an existing invoice instead of creating a new one', async () => {
    renderDialog({ charges: [], existingInvoice: { id: 'inv9', invoice_number: 'INV-000009', balance_paise: 30000 } });
    expect(screen.queryByTestId('collect-discount')).not.toBeInTheDocument();
    expect(screen.getByTestId('collect-total')).toHaveTextContent('₹300');
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('patient-billing/invoices/inv9/payments',
      { amount_paise: 30000, mode: 'cash', reference: null }));
  });

  it('shows the real server reason and stays open when collecting fails', async () => {
    const { toast } = jest.requireMock('sonner');
    (api.post as jest.Mock).mockRejectedValue(new Error('One or more charges are already billed or void'));
    const { onClose } = renderDialog();
    await userEvent.click(screen.getByTestId('collect-submit-btn'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('One or more charges are already billed or void'));
    expect(onClose).not.toHaveBeenCalled();
  });
});
