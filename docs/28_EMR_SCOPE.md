# EMR Module — v1 Scope
# Version: 0.1 | Last updated: October 2, 2026
# Type: Explanation
# Status: Draft — scoping only. 🚫 No tables or code built until Abinash approves the schema (Manifesto rule 13).

## Goal
- EMR = module #2 on the shared platform (see `docs/27_PLATFORM_MODULE_MAP.md`).
- v1 = Patient records, Appointments, Consultation + Rx, Send Rx to the linked pharmacy.
- Code lives in a new `backend/modules/emr/` and `frontend/src/modules/emr/`; pharmacy code untouched.

## Reuse (verified in code)
- Patient = existing `customers` row (per `pharmacy_id`); prescriber = `doctors` row. Both are per-pharmacy today, not shared across pharmacies.
- Login, roles, audit log, store scoping, shared UI = core, reused as-is.
- Clinic is identified by its linked `pharmacy_id` (see decision in doc 27).

## New tables (proposed, all soft-delete, all carry `pharmacy_id`)
| Table | Purpose | Key columns |
|-------|---------|-------------|
| `emr_doctor_schedules` | When a doctor sees patients | doctor_id, weekday, start_time, end_time, slot_minutes |
| `emr_appointments` | A booked visit | customer_id, doctor_id, start_at, end_at, status, reason |
| `emr_consultations` | What happened in the visit | appointment_id, vitals (JSON), complaints, diagnosis, notes, follow_up_date |
| `emr_prescriptions` | The Rx header | consultation_id, rx_number, status |
| `emr_prescription_items` | Medicines on the Rx | product_id (optional), medicine_name, dose, frequency, duration_days, instructions, quantity |

- Appointment status: `booked → checked_in → in_consult → completed`, plus `cancelled`, `no_show`.
- Rx status: `draft → issued → sent_to_pharmacy → dispensed`, plus `cancelled`. Values go in a constants file first (rule 9).

## Permissions (new groups, registered by the module)
- `appointments:view|create|edit|cancel`
- `consultations:view|create|edit`
- `prescriptions:view|create|issue|cancel`

## Build order
1. Schema + migration + models (needs approval).
2. Appointments API + tests → frontend page (calendar/day list, booking).
3. Consultation + Rx API + tests → frontend (notes, vitals, Rx editor, printable Rx).
4. Send Rx to pharmacy: Rx shows in billing; "Fill Rx" prefills a bill; `bills.prescription_id` link.
5. Fresh whole-feature audit as doctor / receptionist / pharmacist (rule 11) before marking done.

## Not in v1 (competitor gaps to revisit)
- Medicine allergy/interaction warnings, lab orders, e-signature, patient-facing booking, teleconsult, ABHA/ABDM integration.
- Fees/billing for consultations (v1 = Rx only).

## Open questions
- Does a doctor log in as a `users` row? (Proposed: yes, `doctors` links to `users` optionally.)
- Clinic with no pharmacy — deferred.
