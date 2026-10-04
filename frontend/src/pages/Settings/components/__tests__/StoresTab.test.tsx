import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StoresTab from '../StoresTab';
import { AuthContext } from '@/App';
import api from '@/lib/axios';

// Regression tests for the Sep 26, 2026 multi-chain Phase 2, Step 3
// "Add a Store" under Settings (docs/26_MULTI_CHAIN_SCOPE.md).

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const ONE_STORE = [{ pharmacy_id: 'p1', name: 'Main Store', city: 'Bengaluru', state: 'Karnataka' }];
const TWO_STORES = [
  ...ONE_STORE,
  { pharmacy_id: 'p2', name: 'Second Store', city: 'Mysuru', state: 'Karnataka' },
];

const renderTab = (user: unknown = { role: 'admin', permissions: ['*'] }) => render(
  <AuthContext.Provider value={{ user } as never}><StoresTab /></AuthContext.Provider>,
);

describe('StoresTab', () => {
  beforeEach(() => jest.clearAllMocks());

  it('lists the existing store(s)', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    renderTab();
    await waitFor(() => expect(screen.getByText('Main Store')).toBeInTheDocument());
  });

  it('tells the admin settings will be copied but numbering starts fresh', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    renderTab();
    await waitFor(() => expect(screen.getByText('Main Store')).toBeInTheDocument());
    await userEvent.click(screen.getByTestId('add-store-btn'));
    expect(screen.getByText(/branding, GST defaults, and thresholds will be copied/)).toBeInTheDocument();
  });

  it('adding a store posts the form and refreshes the list', async () => {
    (api.get as jest.Mock)
      .mockResolvedValueOnce({ data: ONE_STORE })
      .mockResolvedValueOnce({ data: TWO_STORES });
    (api.post as jest.Mock).mockResolvedValue({ data: { pharmacy_id: 'p2', name: 'Second Store' } });

    renderTab();
    await waitFor(() => expect(screen.getByText('Main Store')).toBeInTheDocument());

    await userEvent.click(screen.getByTestId('add-store-btn'));
    await userEvent.type(screen.getByLabelText('Store Name *'), 'Second Store');
    await userEvent.type(screen.getByLabelText('Phone *'), '9800000001');
    await userEvent.type(screen.getByLabelText('Address *'), '2 St');
    await userEvent.type(screen.getByLabelText('City *'), 'Mysuru');
    await userEvent.type(screen.getByLabelText('State *'), 'Karnataka');
    await userEvent.type(screen.getByLabelText('Pincode *'), '570001');

    await userEvent.click(screen.getByText('Add Pharmacy', { selector: 'button[type="submit"]' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      'pharmacies/stores',
      expect.objectContaining({ name: 'Second Store', city: 'Mysuru' }),
    ));
    await waitFor(() => expect(screen.getByText('Second Store')).toBeInTheDocument());
  });

  it('hides Add Pharmacy unless the role is ticked for it', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    const { unmount } = renderTab({ role: 'manager', permissions: ['pharmacies:view'] });
    await waitFor(() => expect(screen.getByText('Main Store')).toBeInTheDocument());
    expect(screen.queryByTestId('add-store-btn')).not.toBeInTheDocument();
    unmount();
    renderTab({ role: 'manager', permissions: ['pharmacies:create'] });
    expect(await screen.findByTestId('add-store-btn')).toBeInTheDocument();
  });

  it('shows the real error reason when adding a store fails', async () => {
    const { toast } = require('sonner');
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    (api.post as jest.Mock).mockRejectedValue({ message: 'Admin access required' });

    renderTab();
    await waitFor(() => expect(screen.getByText('Main Store')).toBeInTheDocument());
    await userEvent.click(screen.getByTestId('add-store-btn'));
    await userEvent.type(screen.getByLabelText('Store Name *'), 'X');
    await userEvent.type(screen.getByLabelText('Phone *'), '9800000001');
    await userEvent.type(screen.getByLabelText('Address *'), 'x');
    await userEvent.type(screen.getByLabelText('City *'), 'x');
    await userEvent.type(screen.getByLabelText('State *'), 'x');
    await userEvent.type(screen.getByLabelText('Pincode *'), '570001');
    await userEvent.click(screen.getByText('Add Pharmacy', { selector: 'button[type="submit"]' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Admin access required'));
  });
});
