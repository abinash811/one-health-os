# Changelog

Every change to PharmaCare, in order, newest first. This is the product's history —
read it to see how PharmaCare has grown over time.

Format follows [Keep a Changelog](https://keepachangelog.com/). Each entry says
**what** changed and **why**, not just a file list.

---

## [Unreleased]

### Added
- **Workspace** (docs/33 W1+W2): every hospital now has a workspace that its logins, roles, pharmacies and clinics belong to. Signing up forms one; places added later join it. Existing standalone pharmacies each got a workspace of one — nothing changed for them.
- **Settings → Organisation → Clinics** (docs/32 P1): clinics are now their own records, separate from pharmacies. Create, edit and deactivate them; who can is decided by the Clinics ticks in a role (administrators always). Places that already used EMR keep working — each got a clinic with the same id.
- New role ticks: View / Create / Edit Clinics and View / Create / Edit Pharmacies.

### Changed
- Team is now the whole workspace (docs/33 W3): every login in the hospital is listed and manageable from any place; the same email can't be added twice in one workspace. The Audit Log shows actions at every place the viewer has access to. Doctors can be linked to any login in the workspace.
- "Stores & chain" is now **Pharmacies**. Adding a pharmacy needs the Create Pharmacies tick (not administrator only), and the person who adds it gets the role they already have there, never administrator.
- Roles now belong to the hospital, not to one pharmacy (docs/32 P0): a place added to a hospital uses its existing roles, and a role made once works everywhere. No one's access changed — existing hospitals' roles were merged by name and permissions (migration `a1c4e7d90b36`).

### Changed
- **EMR now uses the doctor records.** Appointments, the calendar, booking, working hours, prescriptions and the consultation fee all
  point at a doctor profile mapped to the clinic — no longer at a login. A doctor with no login can be scheduled, booked and can
  prescribe. Settings → EMR → Doctors & fees now sets only this clinic's fee; name, registration number and the clinics a doctor
  works at are edited under Settings → Organisation → Doctors.

### Added
- **Doctors are now their own records (Settings → Organisation → Doctors).** A doctor is a profile owned by the hospital — name,
  specialty, qualification, registration number, phone — mapped to the clinics where they practise, with a consultation fee for
  each clinic. No password: logins stay in Team, and a doctor can optionally be linked to one. Outside (referring) doctors are the
  same record with an "External" tick. Existing doctor logins were turned into profiles automatically. New permissions: View
  Doctors / Create & Edit Doctors.

### Fixed
- **First admin had no store access row** (created by `seed_admin.py`): the sidebar store switcher read "Loading…" and clinic pickers
  were empty. The script, a data fix and a safety fallback now cover it, and a new check blocks it happening again.

### Changed
- **One Settings hub, a tab per module.** Settings now has tabs **Organisation** (Team, Roles & Permissions, Stores & chain),
  **EMR** (Clinic profile, Patient ID formats, Patient form, Doctors & fees, Doctor schedules) and **Pharmacy** (the nine
  pharmacy pages), with that module's sections down the left. Each module in the sidebar has its own **Settings** shortcut
  that opens its tab. People only see the tabs and sections they have access to (a clinic manager ticked for EMR settings sees
  only EMR). Unsaved clinic edits survive a visit to Doctor schedules. Old links `/team`, `/emr/settings` and `/emr/schedules`
  forward to the new places; the EMR page tabs are now just Appointments / Calendar / Patients. Mock-up:
  `docs/mockups/31_settings_hub_mock.html` (layout B).
- **Sidebar is now grouped by module.** Three folding sections — **EMR** (Appointments, Calendar, Patients, Clinic Billing),
  **Pharmacy** (Dashboard, Billing, Inventory, Purchases, Customers, Suppliers, Reports, Sch H1 Register) and **Admin** (Audit
  Log, Settings, Team). The module you are in opens by itself; click another heading to open that one instead. A module with
  nothing the user may open is hidden, so a doctor sees only EMR and a cashier only Pharmacy. Collapsed-to-icons mode is
  unchanged. Mock-up: `docs/mockups/30_nav_modules_mock.html`.
- **Clinic billing buttons now follow Roles & Permissions, not role names.** Collect, Cancel invoice and Write Rx show for
  anyone whose role is ticked for them — so any role can create and collect a bill once access is given. Default ticks are
  unchanged. Login and `/auth/me` now include the user's permission list.

### Added
- **Clinic calendar (Practo-style).** New **Calendar** page: doctors side by side for a day, or one doctor's whole week, on a
  time grid built from their working hours. Click an open slot to book (doctor, date and time already filled in), click a visit
  to check in / start / complete / cancel / collect, or drag a booked visit onto another open slot to reschedule — if the slot
  is taken you're told why. A red line marks "now"; walk-ins sit in their own strip; colours match the queue's statuses.
- **Admin is a checkbox, not a role.** Each member now has a clinical role (Doctor, Receptionist, …) plus a separate
  **Administrator** checkbox, so one person can be a Doctor and an admin. Admins get every permission and can manage team,
  roles and settings, and sees the whole sidebar (Team, Settings, Billing…) whatever their clinical role. Existing admins are converted automatically; you can't remove your own admin access. The old
  "admin" role is no longer offered when inviting a member.
- **Patient Billing B4 — the billing desk.** New "Clinic Billing" area: **Pending** (everyone who owes money, split into
  not-invoiced and invoiced-unpaid, filter by source, one-click Collect), **All bills** (search, pay the rest, cancel an
  unpaid invoice with a reason, print), **Receipts**, and **Day closing** (the day's collections by cash/UPI/card and by
  counter). Each patient's complete bill is also a **Billing tab** on their profile. Excel export on each list.
- **Patient Billing B3 — fees on the queue.** The appointments queue now shows each visit's fee (Unpaid / Part-paid /
  Paid with the payment mode), a **Collect** button (discount, part-payment, cash / UPI / card; pays the rest of a
  part-paid invoice), and a "Collected today" card with the day's receipts. Every collection can be printed as an
  invoice with receipt. Doctors can see fees but are not offered Collect.
- **Patient Billing, steps B1–B2 (backend).** A separate module: one account per patient, where every
  service posts a *charge*; each counter invoices and collects its own; the billing desk gets a Pending
  list and a complete bill per patient. Includes invoices (frozen copies), part-payments, receipts,
  day summary, and safeguards against double-charging and overpaying even when two people click at once.
  Doctors now have a consultation fee (Settings → Doctors); it is added to the patient's bill
  automatically at check-in and withdrawn if the visit is cancelled before billing. Medicines stay on the
  pharmacy's own GST bill. Screens for collecting and the billing desk come in B3–B4.
- **EMR Clinic Settings.** New Settings tab: clinic profile and registration number, prescription footer,
  patient ID (UHID) and Rx number formats, default appointment length, a configurable patient
  registration form (hide or require fields — enforced by the server) and doctor profiles (specialty,
  qualification, registration number printed on their prescriptions). Every patient now gets a UHID
  (existing patients were numbered by a migration) and can be searched by it. EMR actions now show
  with readable labels in the Audit Log.
- **EMR patient profile.** Click a patient to see details, allergy warning and every visit with its
  prescription (view / print), and book a new appointment from there. Issuing a prescription now also
  completes the visit, so the queue no longer leaves finished visits "In Consult".
- **EMR step 2: consultation + prescription + printable Rx.** One prescription record per
  visit carries the whole consultation (vitals, complaints, diagnosis, advice, follow-up) plus
  its medicine lines — requested by Abinash so a visit is a single document, not two linked ones.
  - New tables `emr_prescriptions` + `emr_prescription_items` (migration `dc6a0865f1a9`); RX numbers per pharmacy.
  - Draft → issued (locked) / cancelled (reason required); one live Rx per appointment.
  - New `prescriptions:*` permissions — doctor role writes, receptionist can only view.
  - Doctor screen at `/emr/consult/:appointmentId`; "Start consult" in the queue now opens it directly.
  - Medicine name suggestions come from the clinic's own past prescriptions.
  - Printable A4 page at `/emr/prescriptions/:id/print` (Print / Save as PDF).
- **EMR module, step 1 backend (patients, doctor schedules, appointments, live queue).**
  Second platform module after pharmacy (`docs/27`, `docs/28`). EMR has its own
  patients table so it works without the pharmacy module; a doctor is a login user.
  Scheduled visits must land on an open slot in the doctor's working hours (no
  double-booking, enforced by the database too); walk-ins get a per-doctor daily
  token; the queue follows booked → checked in → in consult → completed, with
  cancel (reason required) and no-show. New `receptionist` and `doctor` default
  roles. The endpoint-safety gates (permission, audit, tenant, chain-scope) now
  also scan module routers.
- **EMR module, step 1 screens (Clinic: Appointments, Patients, Doctor Schedules).**
  The receptionist's day view with a live queue (auto-refreshes every 30s):
  check in → start consult → complete, cancel with a required reason, no-show;
  a booking dialog (find or register the patient, pick a free slot or issue a
  walk-in token); a patients register; and per-doctor weekly working hours.
  New "Clinic" sidebar group; receptionist and doctor roles land on the
  Appointments page instead of the pharmacy Dashboard. Built only from the
  shared design-system components.
- **New guardrail: doc content can't change without its 'Last updated'
  line changing too.** Audited every doc's header date against real edit
  history and found the same silent-drift pattern as the token bug, three
  times over: `CLAUDE.md`, `docs/06_COMPONENTS.md`, and
  `docs/08_ARCHITECTURE.md` had genuine content added (some by this exact
  session) with the header never bumped; `docs/12_ERROR_HANDLING.md` had
  been edited on Aug 19 (self-dated in its own added text) with the same
  miss. Fixed all four headers. Added a `.githooks/pre-commit` check that
  blocks a commit touching `CLAUDE.md` or `docs/*.md` content unless the
  "Last updated" line is part of the same diff — verified against both a
  blocked case (content changed, date not) and a passing one (both
  changed) before trusting it.
- **New guardrail: `scripts/design_token_sync_check.py`.** Motion tokens
  (and, found while building this, the `page`/`--bg-app` background color)
  disagreed between `tailwind.config.js` and the design system reference
  for months before being caught by chance in conversation, not by any
  check. This diffs the real token values between the two files and fails
  CI/pre-commit if any disagree — the class of bug, not just the one
  instance, is now structurally caught. Wired into `scripts/design-guard.sh`
  (Rule 8) and `.githooks/pre-commit` (runs whenever either file is
  staged). Verified against a deliberately-introduced mismatch before
  trusting it.

### Fixed
- **Clinic roles and buttons (B5 audit).** Clinics created before the prescription/billing features had doctors and
  front-desk roles missing the new permissions (so doctors couldn't write prescriptions, the desk couldn't take
  fees) — a one-time update fixes every existing clinic without removing anything an admin granted. The desk no
  longer offers buttons a role can't use (doctors: Collect; front desk: Cancel invoice, Write Rx); the front desk can
  now open a finished prescription; "Start consult" no longer sends the front desk to a refused screen; and a
  patient who still owes money can't be deleted.
- **Saved-before-committed bug (all endpoints).** The server was sending "success" to the browser a moment *before* the
  database finished saving, so a quick follow-up request could miss the data (the cause of the random test failures we had been
  calling "flaky"), and a failed save would never have been reported. Every endpoint now finishes saving before replying;
  an automatic check (design-guard Rule 22) stops it coming back.
- **`page` background disagreed too** — `tailwind.config.js` (`#F8FAFB`,
  the real value, matches CLAUDE.md's documented page-root pattern) vs
  `colors_and_type.css`'s `--bg-app` (`#f8f9fa`) — same drift class as the
  motion tokens, caught immediately by the new sync check.
- **Motion tokens had three disagreeing sources of truth.**
  `PharmaCare Design System/colors_and_type.css` (and its `motion.html`
  preview) specified a 7-duration/5-easing scale that was never actually
  wired into `tailwind.config.js` — the real app has always run on a
  different, simpler 4-duration scale. `docs/18_ICONOGRAPHY_MOTION.md`
  disagreed with both, telling developers to use raw arbitrary values
  (`duration-[250ms]`) instead of named tokens at all. Made
  `tailwind.config.js` (already live, already used on the Filter Drawer and
  `MoreMenu`) the single source of truth; updated the reference CSS,
  preview, and doc to match it exactly instead of describing a system that
  was never built.

### Added
- **New shared `<MoreMenu>` component** — the "More options" dropdown used on
  Purchase Detail, Sales Return Detail, and Purchase Return Detail. This
  exact popover shape (a `top-full mt-1` / `shadow-xl` panel) had been
  independently hand-rolled on each of those 3 pages; they'd drifted —
  different backdrop handling, one page's version (`SalesReturnDetail`) had
  no backdrop *and* no outside-click handler at all, so it could only be
  closed by clicking a menu item. One definition now: closes on outside
  click, closes on `Escape`, animates in consistently.
- **New guardrail against this exact kind of drift.** `scripts/design-guard.sh`
  Rule 7 and `.githooks/pre-commit` both now block a new hand-rolled
  `top-full mt-1` dropdown outside of `MoreMenu.tsx` itself.
- **Applied the project's own motion tokens** (`duration-fast/base/slow/slower`,
  `ease-out-smooth`) for the first time — they were defined in
  `tailwind.config.js` but used nowhere in the app. Now on `MoreMenu`'s
  entrance animation and Inventory's Filter Drawer (fade backdrop + slide-in
  panel), both previously instant with no transition.
- **Wired up the design system's specified typography** — IBM Plex Sans
  (body) and Manrope (page titles, via `PageHeader`) were always specified
  in `PharmaCare Design System/colors_and_type.css` but never connected;
  every page silently fell back to the generic system font.

### Fixed
- **`scripts/design-guard.sh` silently stopped running partway through.**
  `set -euo pipefail` combined with `grep | grep -v | wc -l` pipelines meant
  that any rule finding **zero** violations (the good case) made `grep`
  exit 1, which `pipefail` propagated, which `set -e` treated as a script
  failure — aborting before later rules ever ran. Added `|| true` to every
  such pipeline, matching the pattern `.githooks/pre-commit` already used
  correctly. The script now actually reaches every rule on every run.
- **"Could not reach the server" on every Inventory add/search, even though
  the backend was healthy.** Root cause: the frontend called
  `REACT_APP_BACKEND_URL` (`http://localhost:8000`) directly from the
  browser. In a hosted/remote dev environment only the frontend's port is
  typically reachable from the actual browser — the backend port isn't, so
  every direct call failed before it even left the browser (nothing showed
  up in the backend's own access log). Fixed by proxying `/api/*` through
  the frontend's own dev server (`craco.config.js` `devServer.proxy`) and
  making every backend-URL call (`lib/axios.js`/`.ts`, and the handful of
  older pages still building their own `${REACT_APP_BACKEND_URL}/api`
  string) fall back to a same-origin relative path when the env var isn't
  set. Works identically for local dev on one machine and for a remote
  environment where only one port is exposed to the browser.
- **Inventory search failed with a generic "Failed to load inventory" on
  every request.** Root cause: `pharmacy_settings.return_prefix` (added by
  an earlier migration) didn't exist on this dev DB — `alembic upgrade head`
  had never actually been run here, so every `/inventory` call 500'd before
  it could return anything. Applied the pending migrations. Also fixed the
  symptom that hid the real cause: `useInventorySearch.js` swallowed every
  fetch error behind a hardcoded toast instead of `error.message` (Manifesto
  rule #10) — a real backend error now surfaces as its actual reason.
- **A medicine could be added with an expiry date already in the past.**
  `POST /stock/batches` (and editing a batch's expiry via `PUT`) accepted
  any date with no validation — an almost-certain typo (wrong year) on a
  brand-new medicine, now rejected with "Expiry date has already passed."

### Added
- **Rebuilt "Add Medicine" (replaces Add Stock) with a Category-driven fixed
  HSN, fixed GST slabs, and name autocomplete.** Previously HSN and GST were
  free-typed per product, so the same medicine could end up coded two
  different ways depending on who added it. Now: Category (Medicine /
  Surgical / First Aid & Contraceptive / Medical Device) is the only thing a
  pharmacist picks, and HSN is derived server-side from it (never
  client-settable) — the form shows the code plus what it covers so it's not
  a black box. GST is a fixed 0/5/12/18% dropdown. Dosage Form drives whether
  a medicine can be sold loose (tablet/capsule) or only as a whole pack
  (syrup/injection/ointment/drops/powder/inhaler). Medicine Name and
  Manufacturer are autocomplete against a static seed list of ~72 common
  Indian medicines and ~30 manufacturers (`constants/medicineSeedList.js`,
  names only — no pricing or paid data source), picking a match auto-fills
  Category/Dosage Form/Generic Name without overwriting anything the user
  already typed. SKU is auto-generated, never entered manually. Opening
  stock (batch/expiry/qty/MRP) stays optional in the same form, matching how
  the previous `AddStockModal.jsx` already combined the two steps. New
  backend endpoint `GET /products/meta` is the single source of truth for
  the form's Category/GST/Dosage-Form options, so frontend and backend can't
  drift apart on what's valid.
- New `frontend/src/lib/axios.js`/`.ts` `formatValidationError()` helper
  turns FastAPI's native `[{loc, msg}]` 422 body into a clean
  `"field: message"` toast, stripping Pydantic's `"Value error, "` prefix —
  applied globally, not just to this form.

### Fixed
- **The real printed receipt (`PrintReceipt.jsx`) never showed real pharmacy
  details.** It was fetched into `BillingWorkspace` state but only
  `paper_size` was ever extracted from it — name, address, phone, GSTIN,
  Drug License, FSSAI, PAN, header/footer text, and the signature/patient-name
  toggles all silently fell back to a hardcoded "PharmaCare" placeholder (or
  nothing). Every real print a pharmacist made was missing this. Wired the
  full Settings > Receipt & Print data through `useBillActions` into both
  print paths (`Save & Print` and `Print Current Bill`), respecting every
  Show-on-Bill toggle exactly like the backend PDF and the Settings preview
  do.
- **Dev-server ESLint overlay blocked the whole app behind a full-screen
  error screen.** It checks the entire codebase, not changed lines, so any
  pre-existing warning anywhere (there are many — see
  `scripts/eslint_changed_lines.py`) made the app unusable in dev. Previously
  patched with `DISABLE_ESLINT_PLUGIN=true` in `.env.local`, which is
  gitignored by design and so never survives a fresh clone or container.
  Fixed for real this time: removes `ESLintWebpackPlugin` directly in
  `craco.config.js`, which is committed — no per-machine setup needed.
  Real enforcement is unaffected — it already happens at the pre-commit hook
  and in CI, both changed-lines only.

---

## [Unreleased]

### Added
- **Sales Invoice and Sales Return now have separate, configurable number
  sequences.** GST requires each document type to be its own gapless series
  (Rule 46) — sharing one counter would create phantom gaps in the invoice
  series every time a return was issued. New `return_prefix` /
  `return_sequence_number` / `return_number_length` on `PharmacySettings`,
  migrated with a backfill from existing "CN-" return numbers so the new
  atomic counter picks up where the old query-then-increment logic left off.
  `Settings > Bill Sequence` now shows and configures both series for real
  (the "Document Type" column previously showed nothing — see Fixed).
  Removed a dead, unreachable `SALES_RETURN` code path in
  `billing.py::_generate_bill_number` (real returns go through
  `/sales-returns`, never `/bills`).

### Fixed
- **Bill Sequence tab was silently empty.** Two stacked pre-existing bugs:
  `apiUrl.billSequences()` pointed at a URL with no matching backend route
  (404), and `fetchBillSequences` expected `{ sequences: [...] }` when the
  endpoint actually returns a bare array. Removed the dead, broken
  `BILL_SEQUENCES` constant.
- **Saving a sequence's prefix without changing its starting number always
  failed.** The check compared against the *next* number to assign, not the
  *last used* one, so `1 >= 1` blocked a same-number save on any sequence
  that had never been used yet — exactly the case you hit configuring a
  fresh sequence. Now only blocks moving the number backward.
- Bill and receipt labels now say "Bill No." instead of "Invoice No." (real
  PDF and the print-receipt component), matching how pharmacies actually
  label these on paper.

### Changed
- **Print (A4/A5) and Digital bill previews unified.** Pharmacy details,
  compliance numbers, and invoice number/date/payment now live only in the
  header (no more duplicate "Sold By" block). Patient name, phone, and
  referring doctor collapsed into a single line instead of separate
  multi-row blocks — saves vertical space, and Print/Digital now match
  structurally. Same consolidation applied to the real bill PDF.

### Fixed
- **Error toasts now say why, not just "failed."** `useSettings.js` read the
  raw 422 `detail` array directly and, since `toast.error()` can't render an
  array of objects, silently fell back to a hardcoded "Failed to save
  settings" — hiding the actual cause (e.g. an invalid GSTIN) from the user.
  Fixed at the root: the shared axios interceptor (`lib/axios.js`/`.ts`) now
  correctly formats both FastAPI's own validation shape and PharmaCare's
  `{field, message}` shape into one readable string on `error.message`, and
  every caller should read that instead of re-parsing the response itself.
  Also strips Pydantic v2's "Value error, " prefix server-side
  (`settings.py::_validation_errors`) so the message reads naturally — e.g.
  "gstin: Invalid GSTIN format" instead of "gstin: Value error, Invalid
  GSTIN format". New standing rule in `CLAUDE.md` (Manifesto #10) and
  `docs/12_ERROR_HANDLING.md`.
- **Phone and Address are no longer required to save Pharmacy Profile.**
  Only Pharmacy Name is required now — Phone and the full address (street/
  city/state/pincode) are recommended (they print on bills) but a pharmacy
  can save the page without them, matching how Drug License and GSTIN
  already worked. `ProfileCompletionPanel` reflects this — both show as
  optional-with-hint, not blocking.

### Added
- **Bill format split into Print vs Digital, and both now carry real billing
  detail.** Print keeps all 4 paper sizes (thermal 58/80mm, A4, A5) with
  free-text header/footer, unchanged. Digital is a new, separate always-A4
  format for WhatsApp/email/download — image header/footer with height
  control, *and* free-text header/footer, plus its own "Show on Bill"
  toggles (shared setting with Print: GSTIN, DL, FSSAI, PAN, Patient Name,
  Signature). New `print_pan` toggle and `digital_bill_header` /
  `digital_bill_footer` columns on `pharmacy_settings`. Both the Settings
  preview and the real `GET /bills/{id}/pdf` output now include payment
  method, "Ref. By" doctor, and a full item table (manufacturer, HSN,
  schedule, pack size, MRP, discount %, discounted price, GST %, amount) —
  previously only name/batch/price/total were shown, well short of what a
  real pharmacy bill needs. QR "Scan to Reorder" and dual License 20/21
  numbers (seen on a competitor's bill) are intentionally not built — both
  need real new backend features, not a formatting fix.
- **Drug License now required to create bills, not to sign up.** Following
  Stripe's "restricted mode" pattern — the account works everywhere else,
  only billing itself is blocked until a valid, non-expired Drug License
  Number is on file. Blocked at the point of use (BillingWorkspace), with a
  backend backstop on `POST /bills`. `utils/drugLicense.js` is the shared
  source of truth for what "valid" means.
- **Pharmacy Profile now validates server-side and shows completion status.**
  `PUT /settings` previously accepted an untyped dict with zero server-side
  validation — GSTIN/PAN/phone/pincode format checks only existed in the
  React form, so a direct API call could blank the pharmacy's name or save
  garbage. New `PharmacyGeneralUpdate` Pydantic model enforces it for real.
  The page is now two-column: form + a live "Profile Completeness" panel
  distinguishing required-to-save fields from Drug License (required to
  bill) and GSTIN (genuinely optional).
- `scripts/flake8_changed_lines.py` and `scripts/eslint_changed_lines.py` —
  the pre-commit hook's lint checks now only fail on lines actually
  added/changed, not the whole file. Backend files in particular had
  hundreds of pre-existing violations (flake8 was only just made runnable)
  that were blocking unrelated, legitimate commits.
- **Signup now creates a real, separate pharmacy per account (multi-tenancy fix).**
  `POST /auth/register` previously attached every new signup to whichever pharmacy
  was first in the database and let the public form self-select "Admin" as a role —
  a live privilege-escalation hole. Signup is now a 2-step form (Account → Pharmacy)
  that creates a brand-new `Pharmacy` + `PharmacySettings` + all 4 default roles, and
  the signing-up user is always that pharmacy's Admin — no role picker. New shared
  `backend/services/provisioning.py::create_pharmacy_with_defaults()` is the one
  place pharmacy creation happens now, used by both `/auth/register` and the app's
  startup dev-seeder (previously two separate, drifted copies of this logic).
- `USER_ROLE` added to `domainConstants.js` (admin/manager/cashier/inventory_staff).
- `.githooks/pre-commit` — blocks a commit if staged files break a `CLAUDE.md` rule
  (raw `<button>`, hardcoded hex colors, files over 300 lines, direct Shadcn button
  imports, ESLint errors, backend flake8 issues). Explains the exact rule violated
  on every block. Checks only staged files, so pre-existing tech debt elsewhere never
  blocks an unrelated commit.
- `flake8` added to `backend/requirements.txt` — CI's backend lint step referenced it
  but it was never actually installed, so backend linting was silently broken.

### Fixed
- `scripts/design-guard.sh` only scanned `.js`/`.jsx` files. Nearly all shared
  components and several pages are `.tsx`/`.ts`, so the guard was blind to most of
  the codebase. Now scans all four extensions.
- **Not yet fixed, flagged for follow-up:** `backend/seed_admin.py` creates role
  permissions as a nested dict (`{"billing": {"create": True}}`), but the actual
  runtime permission checks in `routers/sales_returns.py` and `routers/settings.py`
  only understand the flat list format (`["billing:create"]`) and silently treat
  anything else as zero permissions. Any pharmacy seeded via `seed_admin.py` —
  including the one seeded in local dev — currently has non-admin roles
  (manager/cashier/inventory_staff) with effectively no permissions in those two
  files' checks. The new `create_pharmacy_with_defaults()` helper uses the correct
  format; `seed_admin.py` itself still needs the same fix.
- Inventory page (`/inventory`) had drifted from the rest of the app's design system:
  a hand-rolled search input and filter button instead of the shared `SearchInput`/
  `AppButton`, a local duplicate `StatusBadge` instead of the real shared one, raw
  `<button>` tags in the filter drawer and empty state, and a hand-rolled pagination
  footer instead of the shared `PaginationBar`. All replaced with the shared
  components so Inventory now matches every other list page. `SearchInput` gained an
  `inputRef` prop and `StatusBadge` gained a `dot` prop (both backward-compatible)
  to support this without forking either component.

---

## How to add an entry

Every time we finish a feature or fix, add a dated entry above `[Unreleased]`
(or add to `[Unreleased]` if it hasn't shipped yet), using this shape:

```md
## [YYYY-MM-DD] Short title of what shipped

### Added / Changed / Fixed / Removed
- What changed, and why it mattered — one line each.
```
