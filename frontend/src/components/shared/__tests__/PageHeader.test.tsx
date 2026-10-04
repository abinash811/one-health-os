import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import api from '@/lib/axios';
import { PlaceProvider } from '@/components/PlaceSwitcher';
import { PageHeader } from '../PageHeader';
import AppButton from '../AppButton';

jest.mock('@/lib/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));

describe('PageHeader', () => {
  it('renders title', () => {
    render(<PageHeader title="Billing" />);
    expect(screen.getByText('Billing')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    render(<PageHeader title="Billing" subtitle="Manage invoices" />);
    expect(screen.getByText('Manage invoices')).toBeInTheDocument();
  });

  it('renders actions slot', () => {
    render(<PageHeader title="Billing" actions={<AppButton>New Bill</AppButton>} />);
    expect(screen.getByRole('button', { name: 'New Bill' })).toBeInTheDocument();
  });

  it('renders breadcrumb above title when provided', () => {
    render(<PageHeader title="Bill Detail" breadcrumb={<nav aria-label="breadcrumb">Billing / #123</nav>} />);
    expect(screen.getByLabelText('breadcrumb')).toBeInTheDocument();
    expect(screen.getByText('Bill Detail')).toBeInTheDocument();
  });

  it('does not render subtitle element when not provided', () => {
    const { container } = render(<PageHeader title="Billing" />);
    expect(container.querySelector('p')).not.toBeInTheDocument();
  });

  it('shows the place switcher next to the title when the app shell provides it, and nothing otherwise', async () => {
    const { container, unmount } = render(<PageHeader title="Billing" />);
    expect(container.querySelector('[data-testid="place-switcher-trigger"]')).not.toBeInTheDocument();
    unmount();
    (api.get as jest.Mock).mockImplementation((url: string) => Promise.resolve({
      data: url.startsWith('users/me/clinics')
        ? [{ clinic_id: 'c1', clinic_name: 'Sunrise Clinic', role_name: 'admin', is_active: true }] : [] }));
    render(<MemoryRouter initialEntries={['/emr/appointments']}><PlaceProvider><PageHeader title="Appointments" /></PlaceProvider></MemoryRouter>);
    expect(await screen.findByText('Sunrise Clinic')).toBeInTheDocument();
    expect(screen.getByText('Appointments')).toBeInTheDocument();
  });
});
