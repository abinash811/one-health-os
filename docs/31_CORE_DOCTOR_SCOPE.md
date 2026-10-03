# Doctors as their own records — Build Plan (owned by the hospital, mapped to clinics, separate from logins)
# Version: 0.2 | Last updated: October 3, 2026
# Type: Explanation
# Status: ✅ APPROVED by Abinash Oct 3, 2026 with all five recommendations. 🚧 P1 (new tables, backfill, API, permissions, Organisation → Doctors screen) BUILT Oct 3, 2026. P2 (EMR switches to the new records) in progress; P3 (pharmacy prescribers) and P4 (contract + audit) not started.
# Build notes: the `practitioner_id` columns on schedules / appointments / prescriptions land in P2's migration (not P1's) so they are never left half-filled while EMR still writes the login id.

## Why (product view)
- Abinash's requirement (Oct 3, 2026): "doctors should be mapped under an entity, while users and doctors are different"; creation lives in **Settings → Organisation → Doctors**.
- Today a doctor *is* a login: `emr_appointments`, `emr_prescriptions` and `emr_doctor_schedules` all point at `users.id`, and the doctor list is "users whose role is `doctor`, or who already have a schedule or profile" (`schedules.py`, `settings.py`).
- Consequences: a doctor who never logs in (visiting consultant, referring doctor) cannot exist; "doctor" is decided by a role *name*; one doctor at two clinics needs two logins; the pharmacy keeps a second, unrelated doctors list.
- Entity = the **hospital** (the organisation). A doctor is created once, then assigned to the clinics where they practise (Abinash's choice, Oct 3, 2026). A standalone clinic is its own entity.

## How others do it
- **OpenMRS — verified:** a *Provider* is a separate table from *User*. A provider "does not have to use or have access to the system (e.g. a doctor at a hospital on the other side of the country used for referrals)", and may optionally link to a person/user ([Provider Management Technical Overview](https://openmrs.atlassian.net/wiki/spaces/Archives/pages/25521025/Provider+Management+Technical+Overview), [Multiple providers per encounter](https://openmrs.atlassian.net/wiki/spaces/projects/pages/27009007/Multiple+providers+per+encounter+Design+Page)).
- **CARE (OHC), Odoo, eVitalRx, Marg:** not verified for this question — no claim made.
- `docs/27` already lists "doctors → Core Practitioner" as a planned promotion; this plan is that step.

## The design
- **New core table `practitioners`** (one row per doctor, per entity):
  - `id`, `chain_id` (NULL for a standalone clinic), `pharmacy_id` (the clinic it was created at), `name`, `specialty`, `qualification`, `registration_no`, `phone`, `email`, `is_external` (true = referring / visiting doctor who is not on staff — what the pharmacy's list holds today), `hospital` (for external doctors), `notes`, `user_id` (nullable, unique per entity — the optional login link), `is_active`, `deleted_at`, timestamps.
- **New table `practitioner_clinics`** — which clinics a doctor practises at:
  - `practitioner_id`, `pharmacy_id` (the clinic), `consultation_fee_paise` (fee is per clinic — it differs between clinics), `is_active`; unique on (practitioner, clinic).
- **Users stay as they are** (login + role in Team). The `doctor` role stays as a *permission bundle for logins*; it no longer decides who is a doctor. A doctor profile may be linked to one login.
- **Re-pointed to `practitioners.id`:** `emr_doctor_schedules`, `emr_appointments`, `emr_prescriptions` (column `doctor_user_id` → `practitioner_id`). Schedules, appointments and prescriptions remain per clinic (they already carry `pharmacy_id`).
- **Pharmacy prescribers (later phase):** the existing `doctors` table is merged into `practitioners` with `is_external = true`, keeping the same ids, so `bills.doctor_id` keeps working with only its foreign key swapped.
- **Replaced:** `emr_doctor_profiles` (its fields move onto `practitioners`; the fee moves to `practitioner_clinics`).
- **Rule:** a module table stores `practitioner_id` only; it never copies a doctor's name or registration number except as a frozen snapshot on a printed record (prescriptions, bills, invoices already do this).

## What the user sees
- **Settings → Organisation → Doctors:** list of the hospital's doctors; **Add doctor** form (profile fields, "Works at" clinic tick-boxes with a fee per clinic, optional "Linked login" picker, active switch). No password anywhere on it.
- **Team** is only logins and roles. Inviting a member can optionally link them to an existing doctor.
- **EMR → Doctor schedules** and the booking dialog / calendar list only the doctors mapped to *this* clinic.
- **EMR → Doctors & fees** becomes a per-clinic view: change this clinic's fee and active flag for each mapped doctor; profile details are edited under Organisation.
- A linked login gets the benefit later: "My queue" opens filtered to their own patients (not built today — nothing filters the queue to the logged-in doctor; new feature, ask first).

## Migration — expand, backfill, switch, contract (each step shippable and reversible until the last)
1. **Expand (additive only):** create `practitioners` and `practitioner_clinics`; add nullable `practitioner_id` to `emr_doctor_schedules`, `emr_appointments`, `emr_prescriptions` (+ indexes).
2. **Backfill (idempotent, dry-run report first):**
   - every user who is a doctor today (role `doctor`, or has a profile, schedule, appointment or prescription) → a practitioner with `user_id` set, fields copied from `emr_doctor_profiles`, one `practitioner_clinics` row for their clinic with the fee;
   - set `practitioner_id` on every schedule, appointment and prescription from its `doctor_user_id`;
   - report any row that cannot be mapped; never touches bills, invoices or stock.
3. **Switch the code:** EMR reads and writes `practitioner_id`; doctor lists come from `practitioners` (mapped to the clinic), not from role names; API responses rename `doctor_user_id` → `doctor_id` and the frontend is updated in the same change.
4. **Pharmacy prescribers:** copy `doctors` rows into `practitioners` (`is_external = true`, same ids); swap `bills.doctor_id` FK; Customers → Doctors tab becomes a filtered view of the same list; the billing workspace doctor picker reads `practitioners`.
5. **Contract:** after the full audit and a clean period, drop `doctor_user_id` columns and `emr_doctor_profiles`; keep the old pharmacy `doctors` table read-only (archived) for an agreed period, then drop — nothing is hard-deleted before then (soft-delete rule).

## Cross-cutting consumers to update in the same change (Manifesto rule 11 — checked in code Oct 3, 2026)
- **Backend:** `models.py` (3 FKs), `routers/appointments.py` (17 uses), `routers/schedules.py` (11), `slots.py` (11), `routers/prescriptions.py` (4, incl. the profile join for the printed Rx), `billing_hooks.py` (fee lookup — now per clinic via `practitioner_clinics`), `routers/settings.py` (`/emr/doctor-profiles` endpoints → replaced), new `core/practitioners` service + router.
- **Pharmacy:** `models/customers.py` `Doctor`, `routers/customers.py` `/doctors` (4 endpoints), `bills.doctor_id` FK and `doctor_name` snapshot, doctor-wise sales report (`reports.py`, groups by name), backup export (`reports.py` dumps `doctors`).
- **Frontend (EMR):** `useCalendarData.ts`, `calendarUtils.ts`, `CalendarGrid`, `AppointmentDetailDialog`, `BookAppointmentModal`, `DoctorSelect`, `DoctorSchedulesPanel`, `ScheduleBlockModal`, `DoctorsCard`, `DoctorProfileModal`, `EmrSettingsPanel`, `VisitTimeline`, Appointments, Calendar, Consultation, PatientProfile, PrescriptionPrint, `types.ts`.
- **Frontend (pharmacy / core):** Customers → `DoctorsTable`, `useCustomers`, `DoctorDropdown`, `buildBillPayload`, bill print views, Reports, `DataBackupTab`, `excelExport.js`, `SettingsHub/sections.tsx` (new Doctors section), sidebar permissions.
- **Audit log:** new entity labels (`practitioner`, `practitioner_clinic`); every create/edit/map/link/deactivate is audited (design-guard Rule 16).
- **Permissions:** new `doctors:view` / `doctors:edit` group (admin `*`; clinic roles get `view`); additive role-sync migration so existing clinics' stored roles get them (habit logged in the RULE MISSES LOG, Oct 3, 2026) — and `scripts/check_default_roles.py` keeps defaults valid.
- **Tests:** many backend tests create doctors with `POST /users` role `doctor` (`test_emr_*`, `test_p0_p1_features`, `test_customers_doctors_permissions`, `test_doctor_record_fields`, `test_doctor_wise_sales_report`, `test_multi_tenancy_isolation`, `test_backup_export`) — helpers and fixtures change; tenant scoping on every practitioner lookup (`get_owned_or_404`, Rule 13) including cross-clinic and cross-hospital isolation tests.
- **Docs:** `docs/09` (tables), `docs/10` (API), `docs/27`, `docs/28`, `docs/30` (the shared-person plan uses the same hospital/clinic scoping — keep the two consistent).

## Build phases (each shippable on its own; stop and re-check after each)
- **P1 Foundation:** new tables + backfill + dry-run report + `core/practitioners` service/API + permissions + **Organisation → Doctors** screen (create, edit, map to clinics, fee per clinic, link a login). EMR keeps working unchanged underneath.
- **P2 EMR switch:** schedules, appointments, prescriptions, fee hook, calendar, booking, print use `practitioner_id`; doctor lists from `practitioners`; EMR Doctors & fees becomes per-clinic.
- **P3 Pharmacy prescribers:** merge `doctors` into `practitioners`; swap the bill FK; Customers → Doctors becomes the shared list; billing doctor picker updated.
- **P4 Contract + whole-feature audit:** drop old columns/table; walk it fresh as hospital admin, clinic receptionist, doctor with and without a login, pharmacist, from zero data; update docs; log misses.

## Decisions needed from Abinash (plain language)
1. **Merge the pharmacy's separate doctors list into the same record?** Recommended: yes, in P3 — one list, with a flag for outside (referring) doctors.
2. **Consultation fee per clinic?** Recommended: yes — the same doctor often charges differently at different clinics.
3. **Who can create doctors?** Recommended: administrators and anyone ticked for `doctors:edit`; receptionists can view and book only.
4. **The `doctor` role:** recommended — keep it as the permissions given to a doctor's login; it stops deciding who counts as a doctor.
5. **Existing doctor logins:** recommended — the backfill links each one to its new profile automatically; a doctor you add later may have no login at all.

## Not in this plan
- "My queue" for a linked doctor login (new feature; ask first).
- Sharing a patient's history between clinics (`docs/30`).
- Doctor availability across clinics (a doctor double-booked at two clinics at the same hour) — flag for the audit; not a P1–P3 item.
