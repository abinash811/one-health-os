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

export interface EmrVitals {
  bp_systolic?: number;
  bp_diastolic?: number;
  pulse?: number;
  temperature_c?: number;
  spo2?: number;
  weight_kg?: number;
}

export interface EmrRxItem {
  id?: string;
  medicine_name: string;
  dosage: string | null;
  frequency: string | null;
  duration_days: number | null;
  instructions: string | null;
  quantity: number | null;
}

/** One prescription = the whole visit: consultation record + medicine lines. */
export interface EmrPrescription {
  id: string;
  rx_number: string;
  status: string;
  appointment_id: string;
  patient_id: string;
  patient_name: string | null;
  doctor_user_id: string;
  doctor_name: string | null;
  vitals: EmrVitals;
  complaints: string | null;
  diagnosis: string | null;
  advice: string | null;
  follow_up_date: string | null;
  issued_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  items: EmrRxItem[];
  patient: { gender: string | null; phone: string | null; age: number | null; allergies: string | null; date_of_birth: string | null } | null;
  clinic: { name: string; address: string; phone: string };
}
