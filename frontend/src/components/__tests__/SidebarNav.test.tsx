import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { Home } from 'lucide-react';
import SidebarNav from '../SidebarNav';

const MODULES = [
  { id: 'emr', label: 'EMR', dot: 'bg-teal-600', items: [{ name: 'Calendar', path: '/emr/calendar', icon: Home }] },
  { id: 'pharmacy', label: 'Pharmacy', dot: 'bg-brand', items: [{ name: 'Billing', path: '/billing', icon: Home }] },
];

const renderAt = (path: string, collapsed = false) => render(
  <MemoryRouter initialEntries={[path]}><SidebarNav modules={MODULES} collapsed={collapsed} /></MemoryRouter>);

describe('SidebarNav', () => {
  it('opens the module the current page belongs to and keeps the others folded', () => {
    renderAt('/emr/calendar');
    expect(screen.getByTestId('nav-calendar')).toBeInTheDocument();
    expect(screen.queryByTestId('nav-billing')).not.toBeInTheDocument();
    expect(screen.getByText('EMR').closest('button')).toHaveAttribute('aria-expanded', 'true');
  });

  it('clicking another module opens it and folds the first', async () => {
    renderAt('/emr/calendar');
    await userEvent.click(screen.getByText('Pharmacy'));
    expect(screen.getByTestId('nav-billing')).toBeInTheDocument();
    expect(screen.queryByTestId('nav-calendar')).not.toBeInTheDocument();
  });

  it('clicking the open module folds it', async () => {
    renderAt('/emr/calendar');
    await userEvent.click(screen.getByText('EMR'));
    expect(screen.queryByTestId('nav-calendar')).not.toBeInTheDocument();
  });

  it('collapsed to icons: every item is a flat link, no module headings', () => {
    renderAt('/emr/calendar', true);
    expect(screen.getByTestId('nav-calendar')).toBeInTheDocument();
    expect(screen.getByTestId('nav-billing')).toBeInTheDocument();
    expect(screen.queryByText('Pharmacy')).not.toBeInTheDocument();
  });
});
