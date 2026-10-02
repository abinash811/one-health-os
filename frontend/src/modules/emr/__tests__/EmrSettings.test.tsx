import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import EmrSettingsPage from '../pages/EmrSettings';
import PatientFormModal from '../components/PatientFormModal';
import { AuthContext } from '@/App';
import api from '@/lib/axios';

// EMR Settings: clinic profile, UHID/Rx formats, patient-form layout, doctor profiles.

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const FORM = { phone: 'optional', alternate_phone: 'optional', age: 'optional', date_of_birth: 'optional',
  gender: 'optional', blood_group: 'optional', city: 'optional', allergies: 'optional', notes: 'optional' };
const SETTINGS = { clinic_name: null, clinic_address: null, clinic_phone: null, clinic_email: null,
  registration_no: null, rx_footer: null, rx_prefix: 'RX-', uhid_prefix: 'UH-', uhid_digits: 6, uhid_next: 8,
  default_slot_minutes: 15, patient_form: FORM,
  fallback: { clinic_name: 'Sunrise Pharmacy', clinic_address: '12 MG Road', clinic_phone: '9876543210' } };
const DOCTORS = [{ user_id: 'd1', name: 'Dr Rao', specialty: null, qualification: null, registration_no: null }];

function mockApi(settings = SETTINGS) {
  (api.get as jest.Mock).mockImplementation((url: string) =>
    Promise.resolve({ data: url.startsWith('emr/doctor-profiles') ? DOCTORS : settings }));
  (api.put as jest.Mock).mockImplementation((_u: string, body: object) => Promise.resolve({ data: { ...settings, ...body } }));
}

const renderPage = (role = 'admin') => render(
  <AuthContext.Provider value={{ user: { role } } as never}>
    <MemoryRouter><EmrSettingsPage /></MemoryRouter>
  </AuthContext.Provider>,
);

describe('EMR Settings page', () => {
  beforeEach(() => jest.clearAllMocks());

  it('loads current values, with the pharmacy record as placeholder for blank clinic fields', async () => {
    mockApi();
    renderPage();
    expect(await screen.findByTestId('set-clinic_name')).toHaveAttribute('placeholder', 'Sunrise Pharmacy');
    expect(screen.getByTestId('set-uhid_prefix')).toHaveValue('UH-');
    expect(screen.getByTestId('uhid-preview')).toHaveTextContent('UH-000008');
    expect(await screen.findByTestId('doctor-row-d1')).toHaveTextContent('Dr Rao');
  });

  it('saves edits, sending blank clinic text as null so printouts fall back to the pharmacy', async () => {
    mockApi();
    renderPage();
    await userEvent.type(await screen.findByTestId('set-registration_no'), 'KMC-123');
    await userEvent.clear(screen.getByTestId('set-uhid_prefix'));
    await userEvent.type(screen.getByTestId('set-uhid_prefix'), 'SUN-');
    expect(screen.getByTestId('uhid-preview')).toHaveTextContent('SUN-000008');
    await userEvent.click(screen.getByTestId('save-settings-btn'));

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = (api.put as jest.Mock).mock.calls[0];
    expect(url).toBe('emr/settings');
    expect(body).toEqual(expect.objectContaining({
      registration_no: 'KMC-123', uhid_prefix: 'SUN-', clinic_name: null, rx_footer: null }));
  });

  it('lets the admin require or hide patient-form fields', async () => {
    mockApi();
    renderPage();
    const row = await screen.findByTestId('form-field-allergies');
    await userEvent.click(within(row).getByText('Required'));
    await userEvent.click(within(screen.getByTestId('form-field-city')).getByText('Hidden'));
    await userEvent.click(screen.getByTestId('save-settings-btn'));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect((api.put as jest.Mock).mock.calls[0][1].patient_form).toEqual(
      expect.objectContaining({ allergies: 'required', city: 'hidden', notes: 'optional' }));
  });

  it('is read-only for non-admins: no Save button, no edit controls', async () => {
    mockApi();
    renderPage('receptionist');
    expect(await screen.findByTestId('settings-readonly-note')).toBeInTheDocument();
    expect(screen.queryByTestId('save-settings-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('set-clinic_name')).toBeDisabled();
    expect(await screen.findByTestId('doctor-row-d1')).toBeInTheDocument();
    expect(screen.queryByTestId('edit-doctor-d1')).not.toBeInTheDocument();
  });

  it('edits a doctor profile', async () => {
    mockApi();
    renderPage();
    await userEvent.click(await screen.findByTestId('edit-doctor-d1'));
    await userEvent.type(screen.getByTestId('dp-specialty'), 'Paediatrics');
    await userEvent.type(screen.getByTestId('dp-registration'), 'KMC-9981');
    await userEvent.click(screen.getByTestId('dp-save-btn'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('emr/doctor-profiles/d1',
      { specialty: 'Paediatrics', qualification: '', registration_no: 'KMC-9981' }));
  });

  it('shows the server reason when a save is refused', async () => {
    const { toast } = jest.requireMock('sonner');
    mockApi();
    (api.put as jest.Mock).mockRejectedValue(new Error('uhid_prefix must be 1-10 letters, numbers or dashes'));
    renderPage();
    await userEvent.click(await screen.findByTestId('save-settings-btn'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('uhid_prefix must be 1-10 letters, numbers or dashes'));
  });

  it('shows the server reason when settings cannot be loaded', async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error('Your role does not have the permission'));
    renderPage();
    expect(await screen.findByText('Your role does not have the permission')).toBeInTheDocument();
  });
});

describe('Patient form follows clinic settings', () => {
  beforeEach(() => jest.clearAllMocks());
  const open = (form: Record<string, string>) => {
    (api.get as jest.Mock).mockResolvedValue({ data: { ...SETTINGS, patient_form: { ...FORM, ...form } } });
    (api.post as jest.Mock).mockResolvedValue({ data: { id: 'p9', name: 'X' } });
    return render(<PatientFormModal open onClose={jest.fn()} onSaved={jest.fn()} />);
  };

  it('hides fields the clinic switched off', async () => {
    open({ blood_group: 'hidden', city: 'hidden' });
    await waitFor(() => expect(screen.queryByTestId('patient-blood_group-input')).not.toBeInTheDocument());
    expect(screen.queryByTestId('patient-city-input')).not.toBeInTheDocument();
    expect(screen.getByTestId('patient-age-input')).toBeInTheDocument();
  });

  it('blocks registration until a required field is filled', async () => {
    open({ allergies: 'required' });
    await screen.findByText(/Allergies \*/);
    await userEvent.type(screen.getByTestId('patient-name-input'), 'Asha Menon');
    await userEvent.click(screen.getByTestId('submit-patient-btn'));
    expect(await screen.findByText('This field is required')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();

    await userEvent.type(screen.getByTestId('patient-allergies-input'), 'None known');
    await userEvent.click(screen.getByTestId('submit-patient-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
  });
});
