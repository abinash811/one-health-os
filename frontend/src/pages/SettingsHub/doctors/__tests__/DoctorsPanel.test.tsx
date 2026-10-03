import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DoctorsPanel from '../DoctorsPanel';
import { AuthContext } from '@/App';
import api from '@/lib/axios';

// Settings → Organisation → Doctors (docs/31_CORE_DOCTOR_SCOPE.md): doctors are profiles, not logins.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const STORES = [
  { pharmacy_id: 'c1', pharmacy_name: 'Main Clinic', role_name: 'admin', is_active: true },
  { pharmacy_id: 'c2', pharmacy_name: 'Branch Clinic', role_name: 'admin', is_active: false },
];
const RAO = {
  id: 'p1', name: 'Dr Rao', specialty: 'Cardiology', qualification: 'MD', registration_no: 'MH-1', phone: null, email: null,
  is_external: false, hospital: null, notes: null, is_active: true, user_id: 'u1', user_name: 'Rao Login',
  user_email: 'rao@clinic.com', clinics: [
    { pharmacy_id: 'c1', pharmacy_name: 'Main Clinic', consultation_fee_paise: 50000, is_active: true },
    { pharmacy_id: 'c2', pharmacy_name: 'Branch Clinic', consultation_fee_paise: null, is_active: true }],
};
const VISITING = { ...RAO, id: 'p2', name: 'Dr Visiting', is_external: true, hospital: 'City Hospital', user_id: null,
  user_name: null, user_email: null, clinics: [], registration_no: null, specialty: null, qualification: null };

function mockApi(doctors: unknown[] = [RAO, VISITING]) {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('users/me/stores')) return Promise.resolve({ data: STORES });
    if (url.startsWith('practitioners/linkable-users')) return Promise.resolve({ data: [{ id: 'u9', name: 'Free Login', email: 'free@clinic.com' }] });
    if (url.startsWith('practitioners')) return Promise.resolve({ data: doctors });
    return Promise.resolve({ data: [] });
  });
}

const renderPanel = (user: unknown = { role: 'admin', permissions: ['*'] }) => render(
  <AuthContext.Provider value={{ user } as never}><DoctorsPanel /></AuthContext.Provider>);

describe('Doctors panel', () => {
  beforeEach(() => { jest.clearAllMocks(); mockApi(); });

  it('lists each doctor with the clinics they work at, the fee there, and their login', async () => {
    renderPanel();
    const row = await screen.findByTestId('doctor-row-p1');
    expect(row).toHaveTextContent('Dr Rao');
    expect(row).toHaveTextContent('Cardiology · MD');
    expect(row).toHaveTextContent('MH-1');
    expect(row).toHaveTextContent('Main Clinic · ₹500');
    expect(row).toHaveTextContent('Branch Clinic');
    expect(row).toHaveTextContent('rao@clinic.com');
    const visiting = screen.getByTestId('doctor-row-p2');
    expect(visiting).toHaveTextContent('External');
    expect(visiting).toHaveTextContent('No clinic');
    expect(visiting).toHaveTextContent('No login');
  });

  it('someone who can only view sees the list but no add / edit / remove, and is told why', async () => {
    renderPanel({ role: 'receptionist', permissions: ['doctors:view'] });
    await screen.findByTestId('doctor-row-p1');
    expect(screen.queryByTestId('add-doctor-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('edit-doctor-p1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('remove-doctor-p1')).not.toBeInTheDocument();
    expect(screen.getByTestId('doctors-readonly-note')).toBeInTheDocument();
  });

  it('shows a friendly empty state', async () => {
    mockApi([]);
    renderPanel();
    expect(await screen.findByText('No doctors yet')).toBeInTheDocument();
  });

  it('shows the real reason when loading fails', async () => {
    (api.get as jest.Mock).mockImplementation((url: string) =>
      url.startsWith('practitioners') ? Promise.reject(new Error('Your role does not have the \'doctors:view\' permission'))
        : Promise.resolve({ data: STORES }));
    renderPanel();
    expect(await screen.findByText(/doctors:view/)).toBeInTheDocument();
  });

  it('"Show inactive" asks the server for inactive doctors too', async () => {
    renderPanel();
    await screen.findByTestId('doctor-row-p1');
    await userEvent.click(screen.getByTestId('show-inactive-doctors'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('practitioners?include_inactive=true'));
  });

  it('adds a doctor with a fee in rupees sent as integer paise, mapped to the current clinic — and no password', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: RAO });
    renderPanel();
    await userEvent.click(await screen.findByTestId('add-doctor-btn'));
    const save = await screen.findByTestId('doc-save-btn');
    expect(save).toBeDisabled();                       // a name is required
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    await userEvent.type(screen.getByTestId('doc-name'), 'Dr New');
    expect(screen.getByTestId('clinic-on-c1')).toBeChecked();   // the clinic you are in
    expect(screen.getByTestId('clinic-on-c2')).not.toBeChecked();
    await userEvent.type(screen.getByTestId('clinic-fee-c1'), '500');
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('practitioners', expect.objectContaining({
      name: 'Dr New', user_id: null, is_external: false,
      clinics: [{ pharmacy_id: 'c1', consultation_fee_paise: 50000 }],
    })));
  });

  it('a doctor on staff needs at least one clinic; an external doctor does not', async () => {
    renderPanel();
    await userEvent.click(await screen.findByTestId('add-doctor-btn'));
    await userEvent.type(await screen.findByTestId('doc-name'), 'Dr Z');
    await userEvent.click(screen.getByTestId('clinic-on-c1'));          // untick the only clinic
    expect(screen.getByTestId('doc-save-btn')).toBeDisabled();
    await userEvent.click(screen.getByTestId('doc-external'));
    expect(screen.getByTestId('doc-save-btn')).toBeEnabled();
    expect(screen.getByTestId('doc-hospital')).toBeInTheDocument();
  });

  it('rejects a negative fee before it reaches the server', async () => {
    renderPanel();
    await userEvent.click(await screen.findByTestId('add-doctor-btn'));
    await userEvent.type(await screen.findByTestId('doc-name'), 'Dr Y');
    await userEvent.type(screen.getByTestId('clinic-fee-c1'), '-5');
    expect(screen.getByTestId('doc-save-btn')).toBeDisabled();
  });

  it('edits a doctor: opens filled in, unticking a clinic drops that mapping, saves to the doctor\'s id', async () => {
    (api.put as jest.Mock).mockResolvedValue({ data: RAO });
    renderPanel();
    await userEvent.click(await screen.findByTestId('edit-doctor-p1'));
    expect(await screen.findByTestId('doc-name')).toHaveValue('Dr Rao');
    expect(screen.getByTestId('clinic-fee-c1')).toHaveValue(500);
    expect(screen.getByTestId('clinic-on-c2')).toBeChecked();
    await userEvent.click(screen.getByTestId('clinic-on-c2'));
    await userEvent.click(screen.getByTestId('doc-save-btn'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('practitioners/p1', expect.objectContaining({
      name: 'Dr Rao', user_id: 'u1', is_active: true,
      clinics: [{ pharmacy_id: 'c1', consultation_fee_paise: 50000 }],
    })));
  });

  it('removes a doctor only after confirming', async () => {
    (api.delete as jest.Mock).mockResolvedValue({ data: {} });
    renderPanel();
    await userEvent.click(await screen.findByTestId('remove-doctor-p1'));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('practitioners/p1'));
  });
});
