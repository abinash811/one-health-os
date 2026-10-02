// Shapes returned by backend/modules/emr/routers (docs/10_API.md → EMR).

export interface EmrPatient {
  id: string;
  /** The clinic's own patient ID, e.g. UH-000123. */
  uhid: string | null;
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
  /** The visit's consultation fee from Patient Billing; null = no fee. */
  fee?: EmrFee | null;
}

export interface EmrFee {
  charge_id: string;
  amount_paise: number;
  status: 'unpaid' | 'part_paid' | 'paid';
  paid_paise: number;
  balance_paise: number;
  mode: string | null;
  invoice_id: string | null;
  invoice_number: string | null;
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
  clinic: {
    name: string; address: string; phone: string; email: string | null;
    registration_no: string | null; footer: string | null;
  };
  doctor: { specialty: string | null; qualification: string | null; registration_no: string | null };
  patient_uhid: string | null;
}

export type FieldState = 'hidden' | 'optional' | 'required';

/** Patient-form fields a clinic can hide or require (name is always required). */
export type PatientFormField =
  'phone' | 'alternate_phone' | 'age' | 'date_of_birth' | 'gender' | 'blood_group' | 'city' | 'allergies' | 'notes';

export interface EmrSettings {
  clinic_name: string | null;
  clinic_address: string | null;
  clinic_phone: string | null;
  clinic_email: string | null;
  registration_no: string | null;
  rx_footer: string | null;
  rx_prefix: string;
  uhid_prefix: string;
  uhid_digits: number;
  uhid_next: number;
  default_slot_minutes: number;
  patient_form: Record<PatientFormField, FieldState>;
  /** What printouts show while the clinic fields above are blank. */
  fallback: { clinic_name: string; clinic_address: string; clinic_phone: string };
}

export interface EmrDoctorProfile {
  user_id: string;
  name: string;
  specialty: string | null;
  qualification: string | null;
  registration_no: string | null;
  /** Default consultation fee in paise; null or 0 = no fee is charged at check-in. */
  consultation_fee_paise: number | null;
}
