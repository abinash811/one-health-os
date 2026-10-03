import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AdminCheckbox from '../AdminCheckbox';
import MembersTable from '../MembersTable';

describe('AdminCheckbox', () => {
  it('reports the new value when clicked', () => {
    const onChange = jest.fn();
    render(<AdminCheckbox checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByTestId('is-admin-checkbox'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('is locked (with a reason) when editing yourself', () => {
    render(<AdminCheckbox checked disabled onChange={jest.fn()} />);
    expect(screen.getByTestId('is-admin-checkbox')).toBeDisabled();
    expect(screen.getByText(/can’t remove your own admin access/)).toBeInTheDocument();
  });
});

describe('MembersTable admin badge', () => {
  const base = { is_active: true, email: 'a@b.com', last_login_at: null };
  const renderTable = (users: unknown[]) => render(
    <MemoryRouter>
      <MembersTable users={users} loading={false} currentUser={{ id: 'me' }} pagination={{ page: 1, totalPages: 1 }}
        onEdit={jest.fn()} onDeactivate={jest.fn()} onActivate={jest.fn()} onResetPassword={jest.fn()} onStoreAccess={jest.fn()} />
    </MemoryRouter>);

  it('shows Doctor + Admin for a doctor who is also an admin', () => {
    renderTable([{ ...base, id: '1', name: 'Dr A', role: 'doctor', is_admin: true }]);
    expect(screen.getByText('doctor')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });

  it('shows no Admin badge for a non-admin doctor', () => {
    renderTable([{ ...base, id: '2', name: 'Dr B', role: 'doctor', is_admin: false }]);
    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
  });
});
