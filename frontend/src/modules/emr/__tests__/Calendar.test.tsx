import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Calendar from '../pages/Calendar';
import { weekdayOf } from '../calendarUtils';
import { today } from '@/utils/dates';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { toast } from 'sonner';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({ ...jest.requireActual('react-router-dom'), useNavigate: () => mockNavigate }));

const DOCTORS = [{ id: 'd1', name: 'Dr Rao', role: 'doctor' }, { id: 'd2', name: 'Dr Iyer', role: 'doctor' }];
const SCHEDULES = ['d1', 'd2'].map((d) => ({
  id: `s-${d}`, doctor_user_id: d, weekday: weekdayOf(today()), start_time: '09:00', end_time: '10:00', slot_minutes: 30, is_active: true,
}));
const APPT = {
  id: 'a1', patient_id: 'p1', patient_name: 'Asha Menon', doctor_user_id: 'd1', doctor_name: 'Dr Rao',
  appointment_date: today(), start_time: '09:00', end_time: '09:30', token_number: 1,
  appointment_type: 'scheduled', status: 'booked', reason: 'Fever', cancel_reason: null,
};
const WALK_IN = { ...APPT, id: 'a2', patient_name: 'Walk Wally', start_time: null, end_time: null, token_number: 2, appointment_type: 'walk_in' };

function mockApi(appts: unknown[]) {
  (api.get as jest.Mock).mockImplementation((url: string) => {
    if (url.startsWith('emr/doctors')) return Promise.resolve({ data: DOCTORS });
    if (url.startsWith('emr/schedules')) return Promise.resolve({ data: SCHEDULES });
    if (url.startsWith('emr/appointments')) return Promise.resolve({ data: appts });
    if (url.startsWith('emr/slots')) return Promise.resolve({ data: [
      { start_time: '09:00', end_time: '09:30', available: false }, { start_time: '09:30', end_time: '10:00', available: true }] });
    return Promise.resolve({ data: [] });
  });
}

const renderPage = (role = 'receptionist') => render(
  <AuthContext.Provider value={{ user: { role } } as never}><MemoryRouter><Calendar /></MemoryRouter></AuthContext.Provider>);

describe('Calendar', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  it('asks the API for exactly the day on screen and draws a column per doctor', async () => {
    mockApi([APPT]);
    renderPage();
    expect(await screen.findByTestId('cal-col-d1')).toBeInTheDocument();
    expect(screen.getByTestId('cal-col-d2')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(`emr/appointments?date_from=${today()}&date_to=${today()}`);
  });

  it('shows the visit on its slot and only offers the free slots for booking', async () => {
    mockApi([APPT]);
    renderPage();
    expect(await screen.findByTestId('cal-event-a1')).toBeInTheDocument();
    expect(screen.queryByTestId('cal-slot-d1-09:00')).not.toBeInTheDocument();
    expect(screen.getByTestId('cal-slot-d1-09:30')).toBeInTheDocument();
    expect(screen.getByTestId('cal-slot-d2-09:00')).toBeInTheDocument();
  });

  it('does not draw cancelled visits (their slot is free again)', async () => {
    mockApi([{ ...APPT, status: 'cancelled' }]);
    renderPage();
    await screen.findByTestId('cal-col-d1');
    expect(screen.queryByTestId('cal-event-a1')).not.toBeInTheDocument();
    expect(screen.getByTestId('cal-slot-d1-09:00')).toBeInTheDocument();
  });

  it('puts walk-ins in their own strip', async () => {
    mockApi([WALK_IN]);
    renderPage();
    expect(await screen.findByText('Walk-ins')).toBeInTheDocument();
    expect(screen.getByTestId('cal-event-a2')).toHaveTextContent('Walk Wally');
  });

  it('opens the booking dialog on the clicked doctor, date and slot', async () => {
    mockApi([]);
    renderPage();
    userEvent.click(await screen.findByTestId('cal-slot-d2-09:30'));
    expect(await screen.findByRole('heading', { name: 'Book appointment' })).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(`emr/slots?doctor_user_id=d2&date=${today()}`));
    await waitFor(() => expect(screen.getByTestId('slot-09:30')).toHaveClass('bg-brand'));
  });

  it('opens a visit\'s details with the next-step button', async () => {
    mockApi([APPT]);
    renderPage();
    userEvent.click(await screen.findByTestId('cal-event-a1'));
    const dialog = await screen.findByTestId('appointment-detail');
    expect(dialog).toHaveTextContent('Asha Menon');
    expect(dialog).toHaveTextContent('Fever');
    userEvent.click(screen.getByText('Check in'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`emr/appointments/a1/status`, { status: 'checked_in' }));
  });

  it('reschedules by dragging a booked visit onto a free slot', async () => {
    mockApi([APPT]);
    (api.put as jest.Mock).mockResolvedValue({ data: {} });
    renderPage();
    const card = await screen.findByTestId('cal-event-a1');
    fireEvent.dragStart(card, { dataTransfer: { setData: jest.fn() } });
    fireEvent.drop(screen.getByTestId('cal-slot-d2-09:30'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('emr/appointments/a1', {
      appointment_date: today(), start_time: '09:30', doctor_user_id: 'd2' }));
    expect(toast.success).toHaveBeenCalled();
  });

  it('shows the real reason when a move is refused', async () => {
    mockApi([APPT]);
    (api.put as jest.Mock).mockRejectedValue(new Error('That slot is already booked'));
    renderPage();
    fireEvent.dragStart(await screen.findByTestId('cal-event-a1'), { dataTransfer: { setData: jest.fn() } });
    fireEvent.drop(screen.getByTestId('cal-slot-d2-09:30'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('That slot is already booked'));
  });

  it('only lets a still-booked visit be dragged', async () => {
    mockApi([{ ...APPT, status: 'checked_in' }]);
    renderPage();
    expect(await screen.findByTestId('cal-event-a1')).toHaveAttribute('draggable', 'false');
  });

  it('week view shows one doctor across seven days', async () => {
    mockApi([APPT]);
    renderPage();
    userEvent.click(await screen.findByText('Week'));
    await waitFor(() => expect(screen.getAllByTestId(/^cal-col-/)).toHaveLength(7));
    expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/emr\/appointments\?date_from=\d{4}-\d{2}-\d{2}&date_to=\d{4}-\d{2}-\d{2}$/));
  });
});
