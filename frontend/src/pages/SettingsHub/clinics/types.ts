export interface Clinic {
  id: string;
  name: string;
  address: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  phone: string | null;
  email: string | null;
  registration_no: string | null;
  is_active: boolean;
  /** True only for a clinic that shares its record with a pharmacy (places that used EMR before clinics were separate). */
  has_pharmacy: boolean;
}
