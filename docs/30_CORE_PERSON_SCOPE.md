# One Person Record — Build Plan (EMR patients + pharmacy customers share one person)
# Version: 0.1 | Last updated: October 3, 2026
# Type: Explanation
# Status: 🚫 PLAN ONLY — not built. Needs Abinash's approval (schema change + data migration). Nothing in this file exists in code yet.

## Why (product view)
- Today one human can exist twice: `emr_patients` (clinic) and `customers` (pharmacy). Nobody sees they are the same person.
- Consequences already visible: a clinic patient who buys medicines has no shared history; dues and visits live in two places; a name or phone corrected in one module stays wrong in the other.
- The product is a core plus pluggable modules (`docs/27`). The person is core data. A module may add its own data about a person, never its own copy of the person.
- Abinash's decision (Oct 3, 2026): build the best long-term design, not a patch ("Always tell the best solution not the patching solution").

## How Open Healthcare Network (CARE) does it — verified in its code (`care/emr/models/patient.py`)
- One global `Patient` table: name, gender, date of birth, phone, address, pincode, blood group.
- No facility owns the patient; every module points at that one record.
- Facility-specific numbers (like our UHID) are separate `PatientIdentifier` rows, configured per facility.
- Not verified: how its pharmacy part uses the patient. Competitors (eVitalRx, Marg, Pharmasoft): not verified — they are pharmacy-only, so they have a customer master but no clinic side.

## The design (hub and spoke)
- **Core table `people`** (new) — identity and contact only:
  - `id`, `pharmacy_id` (tenant, unchanged), `name`, `phone`, `alternate_phone`, `email`, `date_of_birth`, `age`, `gender`, `blood_group`, `address`, `city`, `is_active`, `deleted_at`, timestamps.
- **Pharmacy keeps `customers`**, but it becomes the pharmacy's *profile* of a person:
  - keeps `customer_type`, `gstin`, `credit_days`, `notes`, `is_active`; gains `person_id` (required). Name/phone/age/gender/address move to `people`.
- **EMR keeps `emr_patients`**, as the clinic's *profile* of a person:
  - keeps `uhid`, `allergies`, `notes`, `source`; gains `person_id` (required). Identity columns move to `people`. Its existing soft `customer_id` link is dropped (replaced by the shared `person_id`).
- **Rule:** a module table never copies identity columns; it stores `person_id` only. Core never points at a module table (no FK from `people` to anything in a module).
- **Screens stay as they are:** EMR → Patients lists people with a clinic profile; Pharmacy → Customers lists people with a pharmacy profile. Same record, two lenses. A customer who never sees a doctor simply has no EMR profile.
- **Patient Billing keys on the person** (`pb_*.patient_id` becomes the `person_id`), so clinic fees and later pharmacy/lab/IPD charges land on one account (the goal of `docs/29`).

## What the user sees
- Creating a person in either module first searches `people` by phone and name: "Asha Menon · 98xxxxxx01 already exists — use this person?" Use existing / Create new anyway.
- Phone numbers are shared by families, so the app never merges automatically. It always asks.
- A person with both profiles shows two small chips: "Clinic patient" and "Pharmacy customer". Each module's list shows an "Added in EMR / Pharmacy" badge.
- Editing name or phone in either module changes it everywhere.
- A module that is switched off hides its chip and list; the person still exists.

## Migration — expand, backfill, switch, contract (each step shippable and reversible until the last)
1. **Expand (additive only):** create `people`; add nullable `person_id` (+ index) to `customers` and `emr_patients`. No behaviour change.
2. **Backfill (idempotent, with a dry-run report first):**
   - every `customers` row → a person;
   - every `emr_patients` row → if its `customer_id` is set, reuse that customer's person; else if the same `pharmacy_id` has exactly one customer with the same phone and a near-identical name, reuse it; else a new person;
   - same phone but different names → keep separate and list under "possible duplicates" for a human to review.
   - Never touches bills, invoices, stock, GST or the H1 register.
3. **Switch the code:** both modules read/write identity through one core service (`core/people`); API response shapes stay the same so screens do not break; bills keep their own frozen `customer_name` / `customer_phone` snapshots and `customer_id` (a sale record must not change when a person is edited later).
4. **Patient Billing:** re-key `pb_*.patient_id` from `emr_patients.id` to `person_id` (mapping table from step 2); keep the frozen name/UHID snapshots on charges and invoices.
5. **Contract:** drop the now-unused identity columns from `customers` and `emr_patients`, make `person_id` NOT NULL. Only after a full audit and a clean period.

## Cross-cutting consumers to update in the same change (Manifesto rule 11 — checked in code Oct 3, 2026)
- **Bills** — `bills.customer_id` FK → `customers.id` stays; creating a bill with a new customer creates a person + customer profile; snapshots unchanged (reports read the snapshots: `customer_name` in `reports.py`, `inventory.py`).
- **Customers router** — `POST/GET/PUT/DELETE /customers`, `/customers/search`, `/customers/{id}/stats`, outstanding (`_outstanding_paise_by_customer`): same responses, identity fields now from `people`.
- **EMR patients router** — same, plus UHID stays on the EMR profile.
- **Billing workspace UI** — `PatientCombobox`, `PatientSearchModal` search customers; they must search `people` and show the chips.
- **Customers UI** — `CustomerFormDialog`, `CustomersTable`, `CustomerDetailDialog`, `useCustomers`; **EMR UI** — `PatientFormModal`, Patients, PatientProfile, BookAppointmentModal.
- **Exports** — customers Excel export (`exportCustomersToExcel`), backup/export (`reports.py` dumps `customers`; add `people`), audit-log labels (`AuditLogBadges.tsx`: add `person`).
- **Patient Billing** — accounts, pending list, day closing, EMR queue fee lookup, `billing_hooks.py`.
- **Docs** — `docs/09` (tables), `docs/10` (API), `docs/27`, `docs/28`, `docs/29`, `docs/21`/`25` where they describe customers/patients.
- **Gates/tests** — tenant scoping on every `people` lookup (`get_owned_or_404`, design-guard Rule 13), audit log on every create/edit/link (Rule 16), soft deletes only.

## Build phases (each shippable on its own; stop and re-check after each)
- **P1 Foundation:** expand + core `people` service + backfill + dry-run and duplicates report. No screen changes.
- **P2 EMR switch:** EMR patients read/write via `people`; phone-match prompt on registering a patient; chips.
- **P3 Pharmacy switch:** customers via `people`; phone-match prompt on new customer and in the billing workspace; chips and badges.
- **P4 Billing by person:** re-key Patient Billing; one account shows clinic + pharmacy charges.
- **P5 Contract + whole-feature audit:** drop old columns; walk it as receptionist, doctor, pharmacist, admin from zero data; update docs; log in RULE MISSES LOG if anything was missed.

## Decisions needed from Abinash (plain language)
1. **Who shares a person?** Recommended: people are shared within one clinic/pharmacy (`pharmacy_id`), the same boundary as today — safe and matches our proven tenant checks. A hospital with several clinics sharing one patient across clinics (as OHC does) is a later phase, behind explicit store grants; the table is designed so that can be added without a rewrite.
2. **Same phone, different names:** recommended — always ask, never auto-merge.
3. **Existing duplicates after backfill:** recommended — a "Possible duplicates" list admins review (merge or keep separate); nothing merges silently.
4. **Cleanup timing:** recommended — keep old columns unused for a short period after P3/P4, drop in P5 only after the audit.

## Not in this plan
- Doctors/practitioners as a core record (`doctors` table and doctor users) — separate follow-up.
- Pharmacy "mirror" of EMR prescriptions (step 3 of `docs/28`, on hold).
- Patient-facing app / ABHA ID.
