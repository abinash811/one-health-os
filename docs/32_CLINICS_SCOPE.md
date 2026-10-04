# Clinics (EMR) and Pharmacies as separate things — Build Plan
# Version: 0.7 | Last updated: October 4, 2026
# Type: Explanation
# Status: DIRECTION APPROVED by Abinash Oct 4, 2026 (real separate clinics; new Clinics tick-box; deactivate only; logins stay in Team). 🚫 Nothing built. Roles decision made: hospital-wide roles (Oct 4, 2026). ✅ P0 BUILT Oct 4, 2026 (migration `a1c4e7d90b36`, `services/role_scope.py`, 6 new tests). ✅ P1 BUILT Oct 4, 2026 (`clinics` table + backfill `b2d5f8a1c47e`, `/api/clinics`, `clinics:*` / `pharmacies:*` ticks, Organisation → Clinics + Pharmacies screens, 12 backend + 10 jest tests). P2 next.
# Oct 4, 2026: Workspace plan (docs/33) is complete. P2 split into: **P2a ✅ built** (`user_clinic_access`, `users.clinic_id`, `/users/me/clinics`, `switch-clinic`, admin grant/revoke, creator gets access), **P2b** EMR + patient billing tables to `clinic_id`, **P2c** doctor mapping + Doctors at this clinic + switcher/Team UI, **P2d** contract + deactivate guard. Known limit to revisit in the P3 audit: switching a place takes that place's role (as stores do), so permissions follow the last switch — not yet per-module.
# Supersedes v0.1 (which treated a clinic as a pharmacy row — rejected by Abinash).

## Why (product view)
- Abinash (Oct 4, 2026): **clinics are for EMR; pharmacies are for Pharmacy stores.** Each is created and managed separately, under **Settings → Organisation**.
- Doctor profiles are not logins (docs/31). A clinic's doctor list = which doctor profiles practise there.
- Who may create or manage a clinic or a pharmacy depends on the access ticked in their role — not on being an administrator only. Administrators always have it.
- Closes the open gap named in docs/27 and docs/28: "a clinic with no pharmacy".

## What exists today (verified in code, Oct 4, 2026)
- A clinic **is** a `pharmacies` row. All 8 EMR tables (`emr_patients`, `emr_doctor_schedules`, `emr_appointments`, `emr_prescriptions`, `emr_prescription_items`, `emr_settings`, `emr_doctor_profiles`, plus `practitioner_clinics`) hold `pharmacy_id` pointing at it.
- A login's current place is `users.pharmacy_id`; the role is `users.role_id`; roles (`roles.pharmacy_id`) and the store-access list (`user_store_roles`) are per pharmacy row.
- So today a hospital with a clinic needs a pharmacy record even if it has no pharmacy. That is exactly what has to go.
- docs/27 decision (Oct 2): "EMR tables will reference their clinic and its linked pharmacy" — this plan carries that out. The optional pharmacy link stays optional.

## The design (best long-term)
- **New core table `clinics`:** `id`, `chain_id` (the hospital), `name`, address fields, `phone`, `email`, `registration_no`, `is_active`, `deleted_at`, timestamps. Pharmacies stay in `pharmacies`, untouched.
- **Optional link:** `clinics.linked_pharmacy_id` (nullable) — for a hospital whose clinic has an in-house pharmacy (prescription hand-off later). Not needed to use EMR.
- **EMR tables:** `pharmacy_id` → `clinic_id` on every EMR table (expand → backfill → switch → contract, as docs/31).
- **Existing data — same-id trick:** each pharmacy row that currently has EMR data gets a clinic row with the **same id**. Foreign keys keep working through the move, rollback is easy, nothing is copied twice.
- **`practitioner_clinics`:** `pharmacy_id` → `clinic_id` (fee per clinic stays).
- **Roles become hospital-wide:** a role is owned by the hospital and used in clinics and pharmacies alike (a standalone pharmacy keeps working: its own hospital-of-one). This is an extra expand/backfill/switch step on `roles` and everything reading `roles.pharmacy_id`; its own phase below.
- **Logins ↔ clinics:** (table built in P2, not P1 — nothing reads it before the switcher) new `user_clinic_access` (user, clinic, role) — the same shape as today's `user_store_roles`. Logins stay managed in Team; this only records which clinics a login may open.
- **Switcher:** sidebar shows a Clinics group and a Pharmacies group; the person picks one place at a time. Pharmacy pages use the active pharmacy, EMR pages the active clinic.
- **Doctors:** profile ↔ clinic mapping unchanged in meaning; the Organisation → Doctors "Works at" list now lists clinics (not pharmacies).

## What the user sees (Settings → Organisation)
- **Clinics** (new): list (name, city, doctors, active) · **Add clinic** · open one → details, deactivate, and **Doctors at this clinic** (tick-box + fee per doctor).
- **Pharmacies** (the old "Stores & chain", renamed): only pharmacy stores, same add/manage as today.
- **Access** (role ticks, new group): `clinics:view / create / edit` and `pharmacies:view / create / edit`. Administrators have all. Doctor mapping needs `doctors:edit`.
- Default role sets get the new ticks through an additive migration (habit from RULE MISSES LOG, Oct 3) and `scripts/check_default_roles.py` stays green (Rule 23).

## Migration (each step shippable and reversible until the last)
1. **Expand:** create `clinics`, `user_clinic_access`; add nullable `clinic_id` to the EMR tables and `practitioner_clinics` (+ indexes).
2. **Backfill (idempotent, dry-run report first):** a clinic per pharmacy with EMR data (same id, fields copied, settings stay in `emr_settings`); fill `clinic_id` everywhere; copy each login's access to those clinics; report anything unmappable. Never touches bills, invoices or stock.
3. **Switch the code:** EMR reads/writes `clinic_id`; session carries an active clinic; switcher and Doctors "Works at" read `clinics`.
4. **Contract:** after the whole-feature audit, drop the old EMR `pharmacy_id` columns. Nothing hard-deleted.

## Cross-cutting consumers (Manifesto rule 11)
- **Backend:** `modules/emr/*` (≈100 `pharmacy_id` uses across `models.py`, `slots.py`, `doctors.py`, `settings_service.py`, `billing_hooks.py`, 5 routers), `models/practitioners.py` + `services/practitioners.py` + `routers/practitioners.py`, `routers/chains.py` (pharmacies only), `routers/users.py` (`/users/me/stores`, switch), auth/permission helpers, `constants.py`, seed script, provisioning, backup/export if it dumps EMR.
- **Tenancy gates:** Rules 13, 15–17, 21, 24 apply to every new endpoint; the user-creation gate (Rule 24) extends to clinic access.
- **Patient Billing hook:** the EMR→billing bridge (`billing_hooks.py`) is keyed on the tenant — re-check, fee and pending list per clinic.
- **Audit log:** entities `clinic`, `clinic_access`, `practitioner_clinic`.
- **Frontend:** `SettingsHub/sections.tsx`, `StoresTab.tsx`, `StoreSwitcher.tsx`, `navConfig.js`/`SidebarNav.tsx`, `DoctorFormModal.tsx`, EMR pages, `utils/clinicAccess.ts`, Team store-access UI.
- **Tests:** isolation (cross-hospital, cross-clinic), permissions, backfill, rollback; existing EMR tests use the pharmacy as clinic and must move to clinics.
- **Docs:** `docs/09`, `10`, `15`, `26`, `27`, `28`, `30`, `31`.

## Build phases (stop and re-check after each)
- **P0 Roles at hospital level:** expand `roles` with a hospital owner, backfill, switch permission lookups, keep every current login's permissions identical (proven by test before/after).
- **P1 Foundation (built):** `clinics` table, permissions, Clinics screen (list / add / edit / deactivate), Pharmacies section split. EMR unchanged underneath.
- **P2 EMR move:** `clinic_id` on EMR tables, backfill, switch code, switcher with both groups, Doctors at this clinic.
- **P3 Contract + whole-feature audit:** walk it as admin, clinic manager with only the Clinics tick, receptionist, doctor with and without login, pharmacist; from zero data.

## Decision made (Oct 4, 2026): hospital-wide roles
- **Roles for clinic logins.** A role today belongs to one pharmacy. Options:
  - ✅ **Hospital-wide roles (chosen):** one set of roles per hospital, used in clinics and pharmacies. Cleanest, but moves every role to the hospital level.
  - **Clinic-own roles (stopgap):** each clinic gets its own copy of the default roles, like pharmacies do now. Quicker, but roles drift apart between places.

## Not in this plan
- Prescription hand-off from a clinic to its linked pharmacy (docs/28 step 3 — on hold).
- A doctor double-booked at two clinics (docs/31 audit item).
- Shared patient records across clinics (docs/30 — skipped for now).

## P1 notes (built Oct 4, 2026)
- A place that already used EMR got a clinic with the SAME id (backfill) — it shows in both Clinics and Pharmacies until P2/P3 split them for real.
- Deactivating a clinic is a flag only in P1; the "block while appointments or bills are open" check arrives with P2, when EMR rows carry `clinic_id`.
- Add Pharmacy: the creator now gets the role they already hold at the new pharmacy, not administrator (a non-admin with only `pharmacies:create` must not become an admin).
- Doctors' "Works at" and "Doctors at this clinic" still point at pharmacies until P2.
