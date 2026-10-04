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
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const ONE_STORE = [{ pharmacy_id: 'p1', name: 'Main Store', city: 'Bengaluru', state: 'Karnataka', address: '1 St',
  pincode: '560001', phone: '9800000000', gstin: null, drug_license_number: null, is_active: true }];
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

  it('edits a pharmacy: the form opens filled in and saves with PUT', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    (api.put as jest.Mock).mockResolvedValue({ data: {} });
    renderTab();
    await userEvent.click(await screen.findByTestId('edit-store-p1'));
    expect(screen.getByLabelText('Store Name *')).toHaveValue('Main Store');
    await userEvent.clear(screen.getByLabelText('City *'));
    await userEvent.type(screen.getByLabelText('City *'), 'Mysuru');
    await userEvent.click(screen.getByTestId('store-save-btn'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('pharmacies/stores/p1', expect.objectContaining({ city: 'Mysuru' })));
  });

  it('archives in one click, no confirmation (it can be undone), and shows the reason when refused', async () => {
    const { toast } = require('sonner');
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    (api.put as jest.Mock).mockResolvedValueOnce({ data: {} })
      .mockRejectedValueOnce({ message: "Can't archive Main Store: 2 unfinished bills — finish or delete them first" });
    renderTab();
    await userEvent.click(await screen.findByTestId('archive-store-p1'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('pharmacies/stores/p1', { is_active: false }));
    await userEvent.click(await screen.findByTestId('archive-store-p1'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('unfinished bills')));
  });

  it('can show archived pharmacies and restore one', async () => {
    (api.get as jest.Mock).mockImplementation((url: string) => Promise.resolve({
      data: url.includes('include_archived') ? [{ ...ONE_STORE[0], is_active: false }] : ONE_STORE }));
    (api.put as jest.Mock).mockResolvedValue({ data: {} });
    renderTab();
    await screen.findByText('Main Store');
    await userEvent.click(screen.getByTestId('show-archived-stores'));
    expect(await screen.findByText('Archived')).toBeInTheDocument();
    expect(screen.queryByTestId('edit-store-p1')).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId('archive-store-p1'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('pharmacies/stores/p1', { is_active: true }));
  });

  it('hides edit and archive without the edit tick', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: ONE_STORE });
    renderTab({ role: 'manager', permissions: ['pharmacies:view', 'pharmacies:create'] });
    await screen.findByText('Main Store');
    expect(screen.queryByTestId('edit-store-p1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('archive-store-p1')).not.toBeInTheDocument();
  });
});
