# Workspace — logins, roles and audit belong to the hospital — Build Plan
# Version: 0.4 | Last updated: October 4, 2026
# Type: Explanation
# Status: ✅ APPROVED Oct 4, 2026 ("Yes"). ✅ W1 + W2 BUILT Oct 4, 2026 (migration `c3e6a9d2b58f`, `users.chain_id`, every pharmacy has a workspace, every creation path writes it, `/auth/me` carries `workspace`, gate extended, 7 tests). ✅ W3 BUILT Oct 4, 2026 (Team/users + store-access, doctor login links, audit log now read by workspace via `services/workspace.py`; roles and clinics already were; auth needed no change; Rule 21 gate knows `UserORM.chain_id` is the login boundary; 5 tests). ✅ W4 BUILT Oct 4, 2026 (migration `d4f7b0c3e69a`: `chain_id` NOT NULL on pharmacies, roles, users, clinics, practitioners; role names unique per workspace; email unique per workspace where no duplicate existed; all standalone branches removed; Rule 25 gate `check_workspace_identity.py`). **Workspace plan complete** — next is the EMR move (docs/32 P2) and the whole-feature audit.
# Deviations from the plan below: (1) NO `audit_logs.chain_id` — an entry already records the place it happened at, so workspace audit is read through the place's workspace (19 writers untouched); (2) `users.clinic_id` moves to P2 (nothing reads it before the switcher). Original status: PLAN ONLY. Direction given Oct 4, 2026: "logins should be based on workspace — at hospital level. Under the hospital there can be multiple clinics, multiple pharmacies, multiple doctors, staff."
# Supersedes the Oct 2, 2026 decision in docs/27 to keep `pharmacy_id` as the login tenant. Pharmacy DATA (stock, bills, purchases…) keeps `pharmacy_id`; only core identity moves up.

## Why (product view)
- A hospital is one organisation: one set of staff and roles, many places (clinics, pharmacies). Today a login hangs off a single pharmacy record, so a clinic-only hospital still needs a hidden pharmacy, and a person working at two places needs access rows stitched on top.
- Workspace = the hospital = the existing `chains` row (docs/26). Every login, role and audit entry belongs to one workspace; places live inside it.
- This also removes the "standalone vs. in a chain" branching added in P0/P1 (`role_scope`, `clinic_scope`): every pharmacy gets a workspace, so there is only one path.

## What exists today (verified Oct 4, 2026)
- `users.pharmacy_id` (login's home place, also the "active store"), `roles.pharmacy_id` (+ `chain_id` since P0), `audit_logs.pharmacy_id`, `user_store_roles` (login × pharmacy × role).
- `chains` row only exists after a second pharmacy is added; standalone pharmacies have `chain_id` NULL.
- `current_user.pharmacy_id` is read 182 times in 25 files — most are pharmacy-module data (products, bills, purchases) that stay as they are. Only core identity code (auth, users/Team, roles, audit, permissions helpers, practitioners, clinics, EMR) moves.

## The design
- **Workspace = `chains` row** (table keeps its name; screens say "Workspace"). Every pharmacy gets one — a workspace of one for today's standalone pharmacies.
- **Login:** `users.chain_id` (the workspace, NOT NULL after backfill). A login belongs to exactly one workspace. Email is unique per workspace.
- **Active places:** a login keeps an *active pharmacy* (`users.pharmacy_id`, as today) and gains an *active clinic* (`users.clinic_id`). The module you are in decides which is used — no forced single "place".
- **Access per place:** `user_store_roles` (pharmacies, as today) + new `user_clinic_access` (clinics) — each with the role held there. Roles are workspace-wide (P0).
- **Audit:** `audit_logs.chain_id` added; every entry records the workspace plus the place it happened at.
- **Pharmacy data unchanged:** stock, bills, purchases, customers keep `pharmacy_id`.
- **EMR data (P2, after this):** moves to `clinic_id` as planned in docs/32; patient billing follows its clinic.
- **Registration:** signing up creates the workspace (named by the signer) and its first place; which kind of place (clinic, pharmacy or both) is chosen there.

## Migration — expand, backfill, write both, switch reads, contract
1. **W1 Expand (additive):** `users.chain_id`, `audit_logs.chain_id`, `users.clinic_id` (all nullable); backfill: a workspace for every pharmacy with none, `users.chain_id` and `audit_logs.chain_id` from the user's/entry's pharmacy. Idempotent, with a dry-run report first.
2. **W2 Write both:** every login-creation path (register, Team, seed, forgot-password flows) and every audit write sets `chain_id` as well; gate extends Rule 24; login token/`/auth/me` carry the workspace.
3. **W3 Switch reads, one area at a time:** auth → Team/users → roles → audit log → practitioners → clinics; each area's tenant check uses the workspace through one grant-checked helper; the NULL-chain branches go. Full suite after each area.
4. **W4 Contract:** `users.chain_id` NOT NULL, uniqueness moves (email per workspace, role name per workspace), new gate bans core queries filtering identity tables by `pharmacy_id`. `users.pharmacy_id` stays as the active pharmacy.

## Cross-cutting consumers (Manifesto rule 11)
- **Backend:** `auth.py` (register, login, forgot/reset, me), `auth_helpers.py` (`get_current_user`, `User`, `has_permission`, scope helpers, `get_owned_or_404`), `users.py` (Team, store access, switch store), `settings.py` (roles), `chains.py`, `practitioners.py`, `clinics.py`, `services/role_scope.py`, `services/clinics.py`, `services/hospital.py`, `services/provisioning.py`, `seed_admin.py`, audit writers in every router (`_record_audit` copies).
- **Gates:** Rules 13 (tenant lookups), 15–17, 21, 24 updated; new Rule for identity tables.
- **Frontend:** `AuthContext` user shape, store switcher (places grouped Clinics / Pharmacies), Team and Roles screens, Organisation sections, Audit Log page.
- **Reports/exports:** audit export, backup export (`reports.py`) include workspace identity correctly.
- **Docs:** `docs/09`, `10`, `14` (security), `26`, `27` (decision superseded), `32`, `30`, `31`.
- **Tests:** isolation (cross-workspace never visible), login with same email in two workspaces, role/user uniqueness, backfill and rollback, every creation path.

## Build phases (stop and re-check after each; EMR move waits)
- **W1** Expand + backfill · **W2** Write both · **W3** Switch reads (per area) · **W4** Contract.
- Then **P2** (docs/32): `user_clinic_access`, active clinic, EMR + patient billing to `clinic_id`, Doctors at this clinic, switcher with both groups. **P3** whole-feature audit.

## Decisions needed from Abinash (plain language)
1. **One login = one workspace?** Recommended: yes for now (a person working at two hospitals gets two logins); joining several workspaces with one login is a later feature.
2. **Same email in two workspaces allowed?** Recommended: yes — it already happens in real data; sign-in picks the account whose password matches.
3. **Word on screen:** "Workspace" for the hospital level. Recommended: yes, as you said.

## Not in this plan
- A person belonging to several workspaces with one login.
- Renaming the `chains` table or `pharmacy_id` columns on pharmacy data.
- Billing/subscription per workspace (future).
