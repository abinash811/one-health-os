import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClinicDoctorsModal from '../ClinicDoctorsModal';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const CLINIC = { id: 'c1', name: 'Sunrise Clinic', address: null, city: null, state: null, pincode: null, phone: null,
  email: null, registration_no: null, is_active: true, has_pharmacy: false };
const DOCS = [
  { id: 'd1', name: 'Dr Rao', specialty: 'ENT', registration_no: null, is_external: false, mapped: true, consultation_fee_paise: 50000 },
  { id: 'd2', name: 'Dr Visiting', specialty: null, registration_no: 'MH-2', is_external: true, mapped: false, consultation_fee_paise: null },
];
const renderIt = (canEdit = true) => render(<ClinicDoctorsModal clinic={CLINIC} canEdit={canEdit} onClose={jest.fn()} />);

describe('Doctors at this clinic', () => {
  beforeEach(() => { jest.clearAllMocks(); (api.get as jest.Mock).mockResolvedValue({ data: DOCS }); });

  it('lists every doctor, ticked where they practise, with this clinic\'s fee in rupees', async () => {
    renderIt();
    expect(await screen.findByTestId('clinic-doctor-on-d1')).toBeChecked();
    expect(screen.getByTestId('clinic-doctor-on-d2')).not.toBeChecked();
    expect(screen.getByTestId('clinic-doctor-fee-d1')).toHaveValue(500);
  });

  it('ticking a doctor maps them here with the fee in paise', async () => {
    (api.put as jest.Mock).mockResolvedValue({ data: {} });
    renderIt();
    await userEvent.type(await screen.findByTestId('clinic-doctor-fee-d2'), '300');
    await userEvent.click(screen.getByTestId('clinic-doctor-on-d2'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('clinics/c1/doctors/d2', { consultation_fee_paise: 30000 }));
  });

  it('unticking removes the doctor from this clinic', async () => {
    (api.delete as jest.Mock).mockResolvedValue({ data: {} });
    renderIt();
    await userEvent.click(await screen.findByTestId('clinic-doctor-on-d1'));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('clinics/c1/doctors/d1'));
  });

  it('saves a changed fee for a doctor already here; blank means no fee', async () => {
    (api.put as jest.Mock).mockResolvedValue({ data: {} });
    renderIt();
    const fee = await screen.findByTestId('clinic-doctor-fee-d1');
    await userEvent.clear(fee);
    await userEvent.click(screen.getByTestId('clinic-doctor-save-d1'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('clinics/c1/doctors/d1', { consultation_fee_paise: null }));
  });

  it('is read-only without the edit tick', async () => {
    renderIt(false);
    expect(await screen.findByTestId('clinic-doctor-on-d1')).toBeDisabled();
    expect(screen.queryByTestId('clinic-doctor-save-d1')).not.toBeInTheDocument();
  });

  it('shows the server reason when a change is refused', async () => {
    const { toast } = jest.requireMock('sonner');
    (api.put as jest.Mock).mockRejectedValue(new Error("Your role does not have the 'doctors:edit' permission"));
    renderIt();
    await userEvent.click(await screen.findByTestId('clinic-doctor-on-d2'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Your role does not have the 'doctors:edit' permission"));
  });
});
