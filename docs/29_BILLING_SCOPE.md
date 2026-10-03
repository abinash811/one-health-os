# Patient Billing — Build Plan (clinic, pharmacy, lab, IPD on one account)
# Version: 0.6 | Last updated: October 3, 2026
# Type: Explanation
# Status: ✅ B1–B5 ALL BUILT (Oct 2–3, 2026, approved by Abinash). B5 audit done — findings below. Remaining items are listed under "Not built yet". Decisions taken while building are in "Decisions made in B1/B2" below. Visual mock-up: `docs/mockups/29_billing_mock.html` (8 screens, open in a browser).

## Why (product view)
- A patient's complete bill must be visible in one place: consultation today, medicines and lab tomorrow, beds and nursing when IPD arrives.
- Each counter must still bill its own work (pharmacist at the pharmacy, front desk for the consultation, lab for tests). The billing desk sees everything and chases what is pending.
- Today EMR has no fee or payment at all — a clinic cannot charge a patient.

## How Open Healthcare Network (CARE) does it — verified in its code
- Models `account`, `charge_item`, `charge_item_definition`, `invoice`, `payment_reconciliation` (`care/emr/models`).
- **Account** = one per patient (optionally tied to a primary encounter), holds cached totals: gross, net, paid, balance.
- **Charge item** = one billable line, linked to account + patient + encounter, with `service_resource` (what produced it), quantity, price, status, and `paid_invoice`.
- **Invoice** = bundles chosen charge items of an account; keeps a frozen copy (`charge_items_copy`).
- Pharmacy: dispensing creates charge items on the account, then the pharmacy screen auto-creates the invoice and opens payment (care_fe PR #16921, #16730). The same account is what billing sees.
- Sources: https://github.com/ohcnetwork/care/tree/develop/care/emr/models · https://github.com/ohcnetwork/care_fe/pull/16921

## The design (simple version)
1. **Everything is a charge** on the patient's account. One rule, every module.
2. **Each counter invoices and collects its own charges.** Billing desk can collect anything left.
3. **Billing desk** has: All bills · **Pending** · Receipts · Day closing.
4. **Lab / IPD later** only post charges through the same API — no redesign.
5. Money is integer paise; soft deletes; every action in the Audit Log; numbers never reused.

### Where it lives (product principle, docs/27)
- A separate **Patient Billing module** (`backend/modules/patient_billing/`), not inside EMR: pharmacy, lab and IPD all post to it, so it cannot be owned by one of them.
- Modules talk to it only through its API. The patient is referenced by id (`patient_id` + `patient_source`), with no foreign key into EMR tables.
- Not to be confused with pharmacy's own `bills` (GST tax invoices, stock, H1) — those stay exactly as they are.

### ⚠️ Correction to the mock-up: pharmacy items stay on the pharmacy's GST bill
The mock-up (screen 4) shows medicines on the clinic invoice. For GST, stock and Schedule H1, medicines must be billed by the **pharmacy module** on its own tax invoice. So:
- A pharmacy charge on the account is a **mirror**: `source=pharmacy`, `source_ref=<pharmacy bill id>`, amount and paid/unpaid status copied from that bill.
- The clinic invoice never contains pharmacy lines. Billing desk "Collect" on a pharmacy charge hands off to the pharmacy bill's own payment.
- Clinic services (consultation, lab) are GST-exempt healthcare services in v1 — **to verify with the clinic's accountant** before launch.

## Data (needs approval — 3 new tables + 1 column)
| Table | What it holds |
|-------|---------------|
| `pb_charge_items` | pharmacy_id, patient_id, `source_module` (emr/pharmacy/lab/ipd/manual), `source_ref`, `encounter_ref` (+type: appointment/admission), description, quantity, unit_price_paise, total_paise, status (unbilled/invoiced/paid/void), invoice_id, `idempotency_key` (unique per pharmacy — a retried post never double-charges), void_reason, created_by, deleted_at |
| `pb_invoices` | pharmacy_id, patient_id, `invoice_number` (`INV-000001`), `counter` (front_desk/lab/billing_desk…), status (issued/part_paid/paid/cancelled), gross/discount/net/paid paise, frozen `lines` JSONB, cancel_reason, deleted_at |
| `pb_payments` | pharmacy_id, patient_id, invoice_id (null = advance deposit, for IPD), amount_paise, mode (cash/upi/card), reference, `receipt_number` (`RCT-000001`), received_by, deleted_at |
| column `emr_doctor_profiles.consultation_fee_paise` | The doctor's default fee (set in Settings → Doctors) |
- No `accounts` table in v1: the account is the patient; balances are computed from charges and payments. If IPD needs per-admission accounts, add one then (CARE's shape) — charges already carry `encounter_ref`.
- Invoice/receipt prefixes fixed in v1 (`INV-`, `RCT-`); configurable later like Rx numbers.

## API (all under `/api/billing`, tenant-scoped, permission-checked, audit-logged)
| Endpoint | Purpose |
|----------|---------|
| `POST /charges` | What modules call to post a charge (idempotent via `idempotency_key`) |
| `GET /accounts?status=pending&source=` | Billing desk: patients with money owed, split into not-invoiced / invoiced-unpaid |
| `GET /accounts/{patient_id}` | One patient's complete bill: charges, invoices, payments, totals |
| `POST /invoices` | Freeze chosen unbilled charges into an invoice (optional discount) |
| `POST /invoices/{id}/payments` · `POST /payments/advance` | Take payment (part-payment OK, overpay → advance) |
| `POST /invoices/{id}/cancel` · `POST /charges/{id}/void` | Reason required; paid invoices need a refund (see open questions) |
| `GET /summary/today` | Collected by counter and payment mode — feeds Day closing and the queue card |
- New permissions: `billing:view`, `billing:charge`, `billing:invoice`, `billing:collect`, `billing:void`. Defaults: receptionist (view/charge/invoice/collect), doctor (view), admin (all). Existing pharmacies' roles are not auto-updated — admin grants (same as EMR steps).
- Module-to-module calls use the logged-in user's session today; an API key for external systems comes with the rx-inbox decision (docs/15, on hold).

## Build steps (each shippable, in this order — DB model → router → constants → frontend, tests, docs, live walkthrough with screenshots)
| Step | Scope |
|------|-------|
| **B1** | Tables + migration, charges / invoices / payments / pending API, permissions, pytest (tenant isolation, idempotency, part-pay, void/cancel, numbers never reused) |
| **B2** | Consultation fee: `consultation_fee_paise` on the doctor profile (Settings), fee charge auto-posted when the appointment is **checked in**; voided if cancelled/no-show before payment |
| **B3** | Queue: fee chip + **Collect** dialog (mode, discount, part-pay) + printable invoice/receipt + "Collected today" card |
| **B4** | Patient **Billing** tab (complete bill) + **Billing** page: All bills · Pending · Receipts · Day closing, CSV export |
| **B5** | Whole-feature audit as front desk / doctor / billing desk (rule 11). Pharmacy mirror + lab + IPD hooks are specified here but built with their own modules |

## Decisions made in B1/B2 (Oct 2, 2026)
- API prefix is `/api/patient-billing` (pharmacy already owns `/api/billing`). Permissions are `patient_billing:*` — the pharmacy's `billing:*` group already exists and must not grant clinic billing.
- **Advance deposits and overpayment are deferred to IPD** (nothing to apply them to yet). v1 refuses a payment above the balance, so no half-built advance balance exists.
- **Refunds are not supported**: an invoice with payments cannot be cancelled (409). Unpaid invoices can; their charges go back to unbilled.
- **Discounts**: any role with `patient_billing:invoice` can discount up to the invoice total; every discount is in the Audit Log. (Open question 2 still stands — tighten when decided.)
- **Fee timing = check-in** (recommended option taken; open question 3). **Free follow-ups** not in v1 (question 4).
- The patient is a snapshot (`patient_name`, `patient_uhid`) on each charge/invoice — billing never reads EMR tables.
- EMR → billing is an in-process call to `patient_billing/service.py` (the same functions the HTTP API uses), via `modules/emr/billing_hooks.py`. It becomes an HTTP/API-key call if modules are ever deployed apart.
- Fee cancelled after invoicing is left for the billing desk (no silent loss of a billed charge).

## B3 notes (Oct 2, 2026)
- Billing has its own frontend module `frontend/src/modules/patient_billing/` (Collect dialog, printable invoice, money helpers); the EMR queue only *uses* its public pieces.
- The printable invoice takes its letterhead from EMR Settings when readable and prints without one otherwise — a known small coupling until Core has an organisation profile.
- Collect hides for the doctor role in the UI (backend still enforces `patient_billing:collect`). A cancelled/no-show visit offers no Collect.
- After collecting, the toast has a **Print** action, so the desk stays on the queue by default (fewest clicks); paid rows have *Print receipt* in their ⋮ menu.

## B4 notes (Oct 3, 2026)
- **Collect** (desk row, patient bill) collects what is owed in this order: the patient's unbilled charges as one new invoice, otherwise the balance of their oldest unpaid invoice. A patient with both needs two clicks — the row stays Pending until both are settled.
- **Day closing is a summary view, not a sign-off**: it totals a day's receipts by payment mode (cash = "in the drawer") and by counter. It does not lock the day or record who closed it (pharmacy's `day_end_closings` does; a clinic equivalent is a later decision).
- Patient bill is one component (`AccountBill`) used by the desk's account page and by the **Billing tab** on the EMR patient profile — so both always agree.
- Pharmacy is not in the source filters yet (nothing posts pharmacy mirrors until the pharmacy connector is built).
- Exports are Excel files built in the browser from the loaded page (not the whole filtered set).

## B5 — whole-feature audit (Oct 3, 2026)
Walked fresh from zero data in a real browser as **receptionist**, **doctor** and **admin**, logging every refused request and console error, then checked every consumer of the data (rule 11).

### Found and fixed
| # | Persona | Problem | Fix |
|---|---------|---------|-----|
| 1 | Billing desk (existing clinics) | Stored `doctor`/`receptionist` roles held 8, 13 or 14 permissions — three generations. Clinics created before EMR/billing steps could not write prescriptions or collect fees. New permissions only ever reached *new* clinics | Additive data migration `ccbda72a934b` (nothing an admin granted is removed) + gate `check_default_roles.py` (Rule 23) + RULE MISSES LOG entry |
| 2 | Doctor | Desk offered **Collect / Pay** → 403 | `useClinicAccess` hides what the role can't do |
| 3 | Front desk | Offered **Cancel invoice** → 403 | Hidden for receptionist/doctor |
| 4 | Front desk | **Start consult** redirected to the prescription screen → error page | Front desk stays on the queue; "Write Rx" hidden |
| 5 | Front desk | Could not **view** an issued prescription (opening it tried to *create* one → 403) | New read-only `GET /emr/appointments/{id}/prescription`; the Rx screen reads first, starts one only if none |
| 6 | Reception | Deleting a patient who still owed money orphaned their bill | Delete refused with the amount owed (409) until settled or cancelled |
| 7 | Code | "No charges yet" detected by matching message text | Uses the HTTP 404 status |

### Cross-cutting consumers checked
- **Audit Log:** charges, invoices, payments, voids, cancels and fee posting all appear with readable labels. ✅
- **Exports:** Excel on Pending, All bills, Receipts. ✅ (current page only, not the whole filtered set)
- **Other pages:** patient profile (Billing tab), queue (fee chip, Collected today), Settings (doctor fee), print pages. ✅
- **Pharmacy reports / pharmacy day-end closing:** clinic money is *not* included — by design (separate module, separate cash). The clinic drawer is on its own **Day closing** tab.
- **Soft deletes / money in paise / tenant isolation / permission + audit gates:** every gate passes (`design-guard.sh` Rules 1–23).

### Competitor benchmark (rule 15)
CARE's revenue cycle covers charge capture, invoices, payments, **scheme/insurance coverage, claims and reconciliation, accounting integration** (ohc.network/solutions/hospital-management). Against that, real gaps for us:
- **Insurance / government-scheme coverage and claims** — CARE has it; we have none (v1 is cash/UPI/card, patient-pays).
- **Refunds / credit notes** — blocked today (paid invoices can't be cancelled).
- **Receipt sharing on WhatsApp** — the pharmacy side already has a WhatsApp share modal; clinic receipts don't (it is already planned as EMR Step 4).
- **Packages / bundles, follow-up-free rule, outstanding-balance reminders** — product judgment, not verified against competitors.
- **Advance deposits** — arrive with IPD.

### Not built yet / open (decisions for Abinash)
1. Refunds · 2. Discount limits per role · 3. Free follow-up window · 4. Insurance/schemes · 5. Pharmacy mirror + lab/IPD connectors (built with their modules) · 6. ~~Role-based button hiding is name-based~~ — **Resolved Oct 3, 2026** (Abinash: "anyone can create a bill if access is given"): login and `/auth/me` now return `permissions`, and Collect / Cancel invoice / Write Rx buttons follow the Roles & Permissions ticks, not role names. Default ticks unchanged (only Receptionist collects; tick it for any role to give access).
- Known small risks: patient name/UHID on a charge is a snapshot (a later rename doesn't update old bills); "today" is the server's date (same as appointments) — a clinic far from the server's timezone could see the day roll over at the wrong hour.

## Cross-cutting consumers to check in the same change (rule 11)
- Audit Log labels (`pb_charge_item`, `pb_invoice`, `pb_payment`) · patient profile page (new Billing tab) · queue page (fee chip) · Settings (doctor fee) · CSV export · permissions seed · docs 09/10/15/28 + CHANGELOG.

## Open questions for Abinash
1. **Refunds** after a paid invoice/receipt are cancelled — v1 records a manual refund payment with a reason, or skip until asked?
2. **Discounts** — who may give them (receptionist up to a limit, or admin only)?
3. **Fee timing** — charge at check-in (recommended, so the desk can collect early) or when the consult starts?
4. **Free follow-ups** — e.g. no fee for a revisit within 7 days of the last paid visit (common in India)?
5. **Insurance / government schemes** (CARE supports them) — later, not v1.
6. Existing pharmacy-only users: pharmacy bills unchanged; the account mirror switches on only when both modules are on.
