// Shapes returned by backend/modules/emr/routers (docs/10_API.md → EMR).

export interface EmrPatient {
  id: string;
  name: string;
  phone: string | null;
  alternate_phone: string | null;
  email: string | null;
  date_of_birth: string | null;
  age: number | null;
  gender: string | null;
  blood_group: string | null;
  address: string | null;
  city: string | null;
  allergies: string | null;
  notes: string | null;
  /** Where the record was first created: 'emr' or 'pharmacy'. */
  source: string;
  customer_id: string | null;
  is_active: boolean;
}

export interface EmrDoctor {
  id: string;
  name: string;
  role: string;
}

export interface EmrAppointment {
  id: string;
  patient_id: string;
  patient_name: string | null;
  doctor_user_id: string;
  doctor_name: string | null;
  appointment_date: string;
  start_time: string | null;
  end_time: string | null;
  token_number: number;
  appointment_type: string;
  status: string;
  reason: string | null;
  cancel_reason: string | null;
}

export interface EmrScheduleBlock {
  id: string;
  doctor_user_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  slot_minutes: number;
  is_active: boolean;
}

export interface EmrSlot {
  start_time: string;
  end_time: string;
  available: boolean;
}
