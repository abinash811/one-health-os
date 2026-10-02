import type { EmrSettings, PatientFormField, FieldState } from './types';

/** Editable copy of the settings — text boxes hold plain strings, blank = "not set". */
export interface SettingsDraft {
  clinic_name: string; clinic_address: string; clinic_phone: string; clinic_email: string;
  registration_no: string; rx_footer: string; rx_prefix: string; uhid_prefix: string;
  uhid_digits: number; default_slot_minutes: number;
  patient_form: Record<PatientFormField, FieldState>;
}

export const toDraft = (s: EmrSettings): SettingsDraft => ({
  clinic_name: s.clinic_name || '', clinic_address: s.clinic_address || '', clinic_phone: s.clinic_phone || '',
  clinic_email: s.clinic_email || '', registration_no: s.registration_no || '', rx_footer: s.rx_footer || '',
  rx_prefix: s.rx_prefix, uhid_prefix: s.uhid_prefix, uhid_digits: s.uhid_digits,
  default_slot_minutes: s.default_slot_minutes, patient_form: s.patient_form,
});

/** Blank text becomes null so the backend falls back to the pharmacy record. */
export const toPayload = (d: SettingsDraft) => ({
  ...d,
  clinic_name: d.clinic_name.trim() || null, clinic_address: d.clinic_address.trim() || null,
  clinic_phone: d.clinic_phone.trim() || null, clinic_email: d.clinic_email.trim() || null,
  registration_no: d.registration_no.trim() || null, rx_footer: d.rx_footer.trim() || null,
});
