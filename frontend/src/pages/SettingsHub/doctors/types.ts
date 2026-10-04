export interface DoctorClinic {
  clinic_id: string;
  clinic_name: string;
  /** Integer paise; null = no fee at this clinic. */
  consultation_fee_paise: number | null;
  is_active: boolean;
}

export interface Doctor {
  id: string;
  name: string;
  specialty: string | null;
  qualification: string | null;
  registration_no: string | null;
  phone: string | null;
  email: string | null;
  is_external: boolean;
  hospital: string | null;
  notes: string | null;
  is_active: boolean;
  user_id: string | null;
  user_name: string | null;
  user_email: string | null;
  clinics: DoctorClinic[];
}

export interface ClinicOption { clinic_id: string; clinic_name: string; is_current?: boolean }
export interface LinkableUser { id: string; name: string; email: string }
