# Clinics under Settings → Organisation — Build Plan
# Version: 0.1 | Last updated: October 4, 2026
# Type: Explanation
# Status: PLAN ONLY — 🚫 not built until Abinash approves the decisions at the bottom.

## Why (product view)
- Abinash's requirement (Oct 4, 2026): Settings → Organisation should have a **Clinics** section — create several clinics, and map which doctors work at each.
- Doctors are profiles, not logins (docs/31). A profile can exist for someone who never signs in. Users (logins) get access through roles in Team.
- So "access" here = **which doctor profiles practise at which clinic**. Login access stays in Team.

## What exists today (verified in code, Oct 4, 2026)
- A clinic = a `pharmacies` row; the hospital = a `chains` row (`pharmacies.chain_id`).
- "Add Store" (`POST /pharmacies/stores`, UI: Organisation → "Stores & chain") already creates one. It copies the caller's settings (not invoice counters) and makes the caller admin there.
- Doctor↔clinic mapping already exists: `practitioner_clinics` (fee per clinic). Today it is edited only from the **doctor's** side (Organisation → Doctors → "Works at").
- EMR already lists only the doctors mapped to the current clinic.
- Gap named in docs/27 and docs/28: a clinic with no pharmacy — still deferred.

## The design
- **New section: Organisation → Clinics** (replaces "Stores & chain" — same list, same Add form, better name and more on each row).
- **Clinic list:** name, city, number of doctors, active/inactive.
- **Open a clinic → two parts:**
  - **Details:** name, address, phone, GSTIN. Deactivate (soft — never deleted).
  - **Doctors at this clinic:** every doctor of the hospital with a tick-box and a fee for this clinic. Tick = mapped, untick = removed (soft, revived on re-tick).
- **Add clinic:** same form as Add Store; the new clinic starts with a copy of the creator's settings, as today.
- **Both directions edit the same rows:** ticking a doctor here shows on the doctor's "Works at", and the reverse. No new table, no copy of data.
- **No schema change.** New API only:
  - `GET /clinics` — hospital's clinics with doctor counts.
  - `PUT /clinics/{id}/doctors/{practitioner_id}` — map + fee.
  - `DELETE /clinics/{id}/doctors/{practitioner_id}` — unmap.
  - `PUT /clinics/{id}` — edit details / deactivate.
- **Who can do what:** create / edit / deactivate a clinic = administrators (as Add Store today). Map doctors = admin or `doctors:edit`. `doctors:view` = read only.

## Cross-cutting consumers (Manifesto rule 11)
- **Backend:** `routers/chains.py`, `services/practitioners.py` (mapping helpers reused, not duplicated), `routers/users.py` `/users/me/stores`, store switcher.
- **Tenancy:** only clinics the caller has a grant for (`resolve_chain_scope_pids`, Rule 21); every lookup via `get_owned_or_404` (Rule 13).
- **Audit log:** `clinic` create/edit/deactivate, `practitioner_clinic` map/unmap/fee change (Rule 16).
- **Frontend:** `SettingsHub/sections.tsx` (rename + new panel), `StoresTab.tsx` (moved into Clinics), `doctors/DoctorFormModal.tsx` ("Works at"), `StoreSwitcher.tsx` (hide inactive), EMR doctor lists and calendar.
- **Deactivating a clinic:** must not strand open data — check appointments, bills and stock first; block with a plain reason if anything is open.
- **Tests:** backend (cross-hospital isolation, permissions, audit, revive-on-retick, deactivate block) and jest (list, add, tick/untick, read-only).
- **Docs:** `docs/10` (API), `docs/15` (roadmap), `docs/27`, `docs/28`, `docs/31`.

## Build phases
- **P1:** Clinics list + add + edit + deactivate (backend, UI, tests).
- **P2:** "Doctors at this clinic" tick-boxes + fee.
- **P3:** Whole-feature audit as hospital admin, receptionist, doctor with and without a login, from zero data.

## Decisions needed from Abinash (plain language)
1. **One name or two?** Pharmacy stores are the same records as clinics. Recommended: call the section **Clinics** everywhere; a pharmacy counter is just a clinic that has the Pharmacy module on.
2. **Login access list per clinic** (which logins can open it)? Recommended: not in this section — it stays in Team → store access, so there is one place for logins.
3. **Deactivate vs. delete?** Recommended: deactivate only (compliance data is never deleted).
4. **Who creates clinics?** Recommended: administrators only.

## Not in this plan
- Clinic with no pharmacy (docs/27 open gap).
- A doctor double-booked at two clinics (docs/31 audit item).
- Shared patient records across clinics (docs/30 — skipped for now).
