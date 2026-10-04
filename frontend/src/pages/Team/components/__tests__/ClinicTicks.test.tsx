import React, { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClinicTicks from '../ClinicTicks';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));

const ROLES = [
  { name: 'receptionist', permissions: ['patients:view', 'appointments:view'] },
  { name: 'cashier', permissions: ['billing:create'] },
];

function Harness({ picked }: { picked: string }) {
  const [ids, setIds] = useState<string[]>([]);
  return (<><ClinicTicks value={ids} onChange={setIds} role={picked} roles={ROLES} /><output data-testid="ids">{ids.join(',')}</output></>);
}

describe('Invite dialog clinic ticks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.get as jest.Mock).mockImplementation((url: string) => Promise.resolve({
      data: url.startsWith('users/me/clinics')
        ? [{ clinic_id: 'c1', is_active: true }, { clinic_id: 'c2', is_active: false }]
        : [{ id: 'c1', name: 'Sunrise Clinic' }, { id: 'c2', name: 'North Clinic' }] }));
  });

  it('ticks the clinic you work at when the role is a clinic role', async () => {
    render(<Harness picked="receptionist" />);
    await waitFor(() => expect(screen.getByTestId('ids')).toHaveTextContent('c1'));
    expect(screen.getByTestId('invite-clinic-c1')).toBeChecked();
    expect(screen.getByTestId('invite-clinic-c2')).not.toBeChecked();
  });

  it('leaves everything unticked for a pharmacy role', async () => {
    render(<Harness picked="cashier" />);
    await screen.findByText('Sunrise Clinic');
    expect(screen.getByTestId('ids')).toHaveTextContent(/^$/);
  });

  it('lets you tick another clinic too', async () => {
    render(<Harness picked="receptionist" />);
    await userEvent.click(await screen.findByTestId('invite-clinic-c2'));
    expect(screen.getByTestId('ids')).toHaveTextContent('c1,c2');
  });

  it('renders nothing when there are no clinics', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: [] });
    const { container } = render(<Harness picked="receptionist" />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="clinic-ticks"]')).not.toBeInTheDocument();
  });
});
