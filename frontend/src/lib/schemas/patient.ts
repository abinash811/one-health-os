import { z } from 'zod';

const MOBILE = /^[6-9]\d{9}$/;

// Every field is a plain string here (HTML inputs are strings); the form
// converts age/date_of_birth to what the API expects on submit.
export const patientSchema = z.object({
  name:            z.string().trim().min(1, 'Patient name is required'),
  phone:           z.string().regex(MOBILE, 'Enter a valid 10-digit mobile number').or(z.literal('')),
  alternate_phone: z.string().regex(MOBILE, 'Enter a valid 10-digit mobile number').or(z.literal('')),
  age:             z.string().regex(/^\d{1,3}$/, 'Enter age in years').or(z.literal('')),
  date_of_birth:   z.string(),
  gender:          z.string(),
  blood_group:     z.string().max(5, 'Too long'),
  city:            z.string(),
  allergies:       z.string(),
  notes:           z.string(),
});

export type PatientFormValues = z.infer<typeof patientSchema>;
