import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Patients from '../pages/Patients';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const patient = (over: Record<string, unknown>) => ({
  id: 'p1', name: 'Asha Menon', phone: '9876543210', alternate_phone: null, email: null,
  date_of_birth: null, age: 34, gender: 'female', blood_group: null, address: null, city: null,
  allergies: 'Penicillin', notes: null, source: 'emr', customer_id: null, is_active: true, ...over,
});
const page = (rows: unknown[]) => ({
  data: { data: rows, pagination: { page: 1, page_size: 20, total_items: rows.length, total_pages: 1 } },
});

const renderPage = () => render(<MemoryRouter><Patients /></MemoryRouter>);

describe('EMR Patients', () => {
  beforeEach(() => jest.clearAllMocks());

  it('lists patients and says where each record was added', async () => {
    (api.get as jest.Mock).mockResolvedValue(page([patient({}), patient({ id: 'p2', name: 'Ravi K', source: 'pharmacy', age: 51, gender: 'male', allergies: null })]));
    renderPage();

    await waitFor(() => expect(screen.getByTestId('patient-row-p1')).toBeInTheDocument());
    expect(screen.getByText('Added in EMR')).toBeInTheDocument();
    expect(screen.getByText('Added in pharmacy')).toBeInTheDocument();
    expect(screen.getByText('34 y · female')).toBeInTheDocument();
    expect(screen.getByText('Penicillin')).toBeInTheDocument();
  });

  it('shows an empty state for a clinic with no patients', async () => {
    (api.get as jest.Mock).mockResolvedValue(page([]));
    renderPage();
    await waitFor(() => expect(screen.getByText('No patients yet')).toBeInTheDocument());
  });

  it('registers a patient with blanks sent as null', async () => {
    (api.get as jest.Mock).mockResolvedValue(page([]));
    (api.post as jest.Mock).mockResolvedValue({ data: patient({}) });
    renderPage();

    await userEvent.click(await screen.findByTestId('add-patient-btn'));
    await userEvent.type(await screen.findByTestId('patient-name-input'), 'Asha Menon');
    await userEvent.type(screen.getByTestId('patient-phone-input'), '9876543210');
    await userEvent.click(screen.getByTestId('submit-patient-btn'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('emr/patients', expect.objectContaining({
      name: 'Asha Menon', phone: '9876543210', alternate_phone: null, age: null, allergies: null,
    })));
  });

  it('rejects an invalid mobile number before calling the API', async () => {
    (api.get as jest.Mock).mockResolvedValue(page([]));
    renderPage();

    await userEvent.click(await screen.findByTestId('add-patient-btn'));
    await userEvent.type(await screen.findByTestId('patient-name-input'), 'Asha');
    await userEvent.type(screen.getByTestId('patient-phone-input'), '12345');
    await userEvent.click(screen.getByTestId('submit-patient-btn'));

    expect(await screen.findByText('Enter a valid 10-digit mobile number')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('deletes a patient only after confirming', async () => {
    (api.get as jest.Mock).mockResolvedValue(page([patient({})]));
    (api.delete as jest.Mock).mockResolvedValue({ data: {} });
    renderPage();

    await userEvent.click(await screen.findByTestId('delete-patient-p1'));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('emr/patients/p1'));
  });
});
