import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StoreAccessModal from '../StoreAccessModal';
import api from '@/lib/axios';

// Regression tests for the Sep 26, 2026 multi-chain Phase 2, Step 3
// Team-page store-access grant/revoke (docs/26_MULTI_CHAIN_SCOPE.md).

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const STORES = [
  { pharmacy_id: 'p1', name: 'Main Store', city: 'Bengaluru' },
  { pharmacy_id: 'p2', name: 'Second Store', city: 'Mysuru' },
];
const MEMBER = { id: 'u1', name: 'Priya' };

describe('StoreAccessModal', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows an ungranted store with a Grant control and a granted one with Revoke', async () => {
    (api.get as jest.Mock).mockImplementation((url: string) =>
      url.includes('store-access')
        ? Promise.resolve({ data: [{ pharmacy_id: 'p1', pharmacy_name: 'Main Store', role_name: 'cashier' }] })
        : Promise.resolve({ data: STORES }));

    render(<StoreAccessModal member={MEMBER} open onClose={jest.fn()} />);

    await waitFor(() => expect(screen.getByTestId('grant-store-p2')).toBeInTheDocument());
    expect(screen.getByTestId('revoke-store-p1')).toBeInTheDocument();
  });

  it('granting access posts only the store (no role) and refreshes', async () => {
    (api.get as jest.Mock)
      .mockResolvedValueOnce({ data: STORES })
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: STORES })
      .mockResolvedValueOnce({ data: [{ pharmacy_id: 'p1', pharmacy_name: 'Main Store', role_name: 'manager' }] });
    (api.post as jest.Mock).mockResolvedValue({ data: { message: 'ok' } });

    render(<StoreAccessModal member={MEMBER} open onClose={jest.fn()} />);
    await waitFor(() => expect(screen.getByTestId('grant-store-p1')).toBeInTheDocument());

    expect(screen.queryByTestId('role-select-p1')).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId('grant-store-p1'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      'users/u1/store-access', { pharmacy_id: 'p1' }));
  });

  it('revoking access calls delete and shows the real error reason on failure', async () => {
    const { toast } = require('sonner');
    (api.get as jest.Mock).mockImplementation((url: string) =>
      url.includes('store-access')
        ? Promise.resolve({ data: [{ pharmacy_id: 'p1', pharmacy_name: 'Main Store', role_name: 'cashier' }] })
        : Promise.resolve({ data: STORES }));
    (api.delete as jest.Mock).mockRejectedValue({ message: "Cannot remove someone's only store access" });

    render(<StoreAccessModal member={MEMBER} open onClose={jest.fn()} />);
    await waitFor(() => expect(screen.getByTestId('revoke-store-p1')).toBeInTheDocument());
    await userEvent.click(screen.getByTestId('revoke-store-p1'));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('users/u1/store-access/p1'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Cannot remove someone's only store access"));
  });
});
