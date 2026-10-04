# EMR Module — v1 Scope (clinic-day flow)
# Version: 0.9 | Last updated: October 4, 2026
# Type: Explanation
# Status: Steps 1–2 built (Oct 2, 2026); steps 3–5 not started. Schema decisions live in docs/09_DATABASE.md

## Approach
- EMR first: design the clinic day, then decide where the pharmacy plugs in.
- EMR = module #2 on the shared platform (`docs/27_PLATFORM_MODULE_MAP.md`). Hospital = a chain; each clinic is linked to one pharmacy.

## The clinic day, by person

### 1. Receptionist — "who is here, who is next?"
- Find or register a patient in seconds (phone number first).
- Book, reschedule, cancel a visit; walk-ins join today's queue.
- Live queue: waiting → with doctor → done.
- Pain solved: paper registers, double-booking, "is the doctor free?"

### 2. Doctor — "see the patient, write the Rx, move on"
- Open the next patient with history: past visits, past medicines, allergies noted.
- Record complaints, vitals, diagnosis, notes with minimal typing.
- Write the Rx fast: medicine search with smart defaults (dose, frequency, duration), repeat last Rx in one click.
- See whether the clinic's pharmacy has the medicine in stock while prescribing.
- Set follow-up date; print or send the Rx.
- Pain solved: handwritten Rx, patients forgetting what was prescribed, medicines that are out of stock.

### 3. Patient — "get my medicines and not lose my Rx"
- Gets the Rx on WhatsApp/print right after the visit.
- Chooses: collect at the clinic's pharmacy, or get it delivered.
- Gets a follow-up reminder.
- Pain solved: lost slips, walking to a pharmacy that doesn't stock the medicine.

### 4. Pharmacist — "Rx arrives, I fill it"
- Rx appears in a pharmacy "incoming Rx" list, already linked to the patient.
- "Fill Rx" prefills a bill; substitutions and out-of-stock items flagged back to the doctor.
- Dispensed status flows back, so the doctor sees what the patient actually took.
- Pain solved: re-typing Rx into billing, phone calls to the doctor, wrong-medicine errors.

## Where EMR and pharmacy connect (the real product value)
| Moment | EMR side | Pharmacy side (existing code) |
|--------|----------|-------------------------------|
| Prescribing | Stock visibility while writing Rx | `products` / `stock_batches` availability |
| Rx issued | Rx saved to the visit | Incoming-Rx list for the linked pharmacy |
| Dispensing | Doctor sees "dispensed" | Bill created from Rx (prefilled lines) |
| Compliance | Rx is the legal prescription | Schedule H1 register can reuse the Rx's doctor + patient |
| Repeat patient | History shows past medicines | Past bills for the same patient |

## Reuse (verified in code)
- Patient = existing `customers` row; prescriber = existing `doctors` row — both per-pharmacy today.
- Login, roles, audit log, store scoping, shared UI = core, reused as-is.

## Build order (each step shippable on its own)
1. Patients + appointments + live queue (receptionist can run the day).
2. Consultation + Rx editor + printable Rx (doctor can run the day). **Built Oct 2, 2026** — design decided with Abinash:
   - ONE prescription record per visit holds the consultation (vitals, complaints, diagnosis, advice, follow-up) AND the medicine lines — no separate consultation entity. Tables: `emr_prescriptions` + `emr_prescription_items` (see `docs/09_DATABASE.md`).
   - Medicines are free text, with suggestions from the clinic's own prescribing history (no drug catalog yet).
   - Rx lifecycle: draft (editable) → issued (locked, printable) / cancelled (reason required; frees the visit for a new Rx).
   - Print = browser print page (clean A4, Print / Save as PDF). Doctor-only writes; receptionist can view.
3. Rx → pharmacy incoming list → Fill Rx into a bill → dispensed status back. **On hold.** Design when resumed: pharmacy owns a public `rx-inbox` API (per-pharmacy API key); EMR is just one client of it, so a pharmacy can use any external EMR.
3b. **Calendar** `/emr/calendar` — **Built Oct 3, 2026** (Abinash: "a calendar like Practo has"). No schema change: a time-grid view of the same appointments + doctor schedules. Day view = one column per doctor; Week view = one doctor, seven days. Working hours white, off-hours grey, red "now" line, walk-ins in their own strip, colour by status (cancelled / no-show hidden — their slot is free again). Click an open slot → booking dialog pre-filled (doctor, date, time); click a visit → details + check in / start / complete / cancel / collect; drag a still-booked visit onto another open slot to reschedule (API refuses a taken or off-hours slot with the reason). Native drag-and-drop, no new library. Not yet: leave / blocked time (needs a table — ask first), month view, resize-to-change-length.
4. Whatsapp send + follow-up reminders.
5. Fresh whole-feature audit as receptionist / doctor / pharmacist / patient (Manifesto rule 11).

## Settings (built Oct 2, 2026 — Abinash: "doctors, clinics, UHID configuration, patient form and other things")
- **Where it lives (Oct 3, 2026):** Settings → **EMR** tab (`/settings/emr/...`), reached from the sidebar's EMR → Settings. Sections: Clinic profile, Patient ID formats, Patient form, Doctors & fees (this clinic's fee per doctor), Doctor schedules. **Doctors themselves are core records** (Settings → Organisation → Doctors, `docs/31_CORE_DOCTOR_SCOPE.md`): a doctor is a profile, not a login, mapped to the clinics where they practise. Old `/emr/settings` and `/emr/schedules` redirect there.
- Clinic profile (name, address, phone, registration no., Rx footer) — blank fields fall back to the pharmacy record.
- UHID prefix/length and Rx prefix — formats change for new records only; numbers are never reused or restarted.
- Patient form: each optional field can be hidden / optional / required (name always required); enforced by the API, not just the screen.
- Doctor profiles (specialty, qualification, registration no.) printed on their prescriptions.
- Everyone in the clinic can read; only the admin can change (`emr_settings:edit`).
- Not yet: clinic logo (needs file upload), multiple locations per clinic, per-doctor Rx templates.

## Not in v1 — competitor gaps to revisit (rule 15)
- Allergy/interaction warnings, lab orders, e-signature, patient self-booking, teleconsult, ABHA/ABDM, consultation fee billing.

## Open questions for Abinash
- Does the doctor log in with their own user account? (Assumed yes.)
- Clinic with no linked pharmacy — ✅ solved Oct 4, 2026: clinics are their own records (docs/32); EMR data belongs to a clinic (`clinic_id`), no pharmacy needed.
- Is the WhatsApp send in v1 or step 4 as written?
