# Patient Billing — Build Plan (clinic, pharmacy, lab, IPD on one account)
# Version: 0.2 | Last updated: October 2, 2026
# Type: Explanation
# Status: B1 + B2 BUILT (Oct 2, 2026, approved by Abinash); B3–B5 not started. Decisions taken while building are in "Decisions made in B1/B2" below. Visual mock-up: `docs/mockups/29_billing_mock.html` (8 screens, open in a browser).

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

## Cross-cutting consumers to check in the same change (rule 11)
- Audit Log labels (`pb_charge_item`, `pb_invoice`, `pb_payment`) · patient profile page (new Billing tab) · queue page (fee chip) · Settings (doctor fee) · CSV export · permissions seed · docs 09/10/15/28 + CHANGELOG.

## Open questions for Abinash
1. **Refunds** after a paid invoice/receipt are cancelled — v1 records a manual refund payment with a reason, or skip until asked?
2. **Discounts** — who may give them (receptionist up to a limit, or admin only)?
3. **Fee timing** — charge at check-in (recommended, so the desk can collect early) or when the consult starts?
4. **Free follow-ups** — e.g. no fee for a revisit within 7 days of the last paid visit (common in India)?
5. **Insurance / government schemes** (CARE supports them) — later, not v1.
6. Existing pharmacy-only users: pharmacy bills unchanged; the account mirror switches on only when both modules are on.
