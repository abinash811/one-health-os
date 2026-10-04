# PharmaCare — Claude Code Master Reference
# Version: 2.34 | Last updated: October 4, 2026
# Read this file at the start of every session.
# All rules live in /docs — this file is the index and quick-reference only.

---

## THE PHARMACARE MANIFESTO

> **Scope (Oct 2, 2026):** every rule, skill, design token, and gate in this file applies to ALL modules of the platform — Pharmacy and EMR alike — not only pharmacy screens. See `docs/27_PLATFORM_MODULE_MAP.md`, `docs/28_EMR_SCOPE.md`. **Product principle:** open-core platform (like Open Healthcare Network) — Pharmacy is a module that plugs into Core, EMR is a separate module, and modules connect only through documented APIs, never shared tables (docs/27 → Product principle).

1. **One component, one way.** Every button is `<AppButton>`. Every page header is `<PageHeader>`. Every tab bar is `<PageTabs>`. Every "More options" dropdown is `<MoreMenu>`. No raw `<button>` tags, no inline title `<div>`, no custom tab UI, no hand-rolled `top-full mt-1` popover anywhere.
2. **Design tokens, not hex.** `bg-brand`, `hover:bg-brand-dark`, `text-brand`, `border-brand`. Never `#4682B4`, never `#3a6fa0`, never `bg-[#anything]` in component code.
3. **Every page looks like the same product.** Same header height, same tab underline, same button weights. This is what broke when 21 raw `<button>` tags (BillingWorkspace, Dashboard — some written April 2026, before `<AppButton>` existed) sat failing CI for months: same app, visibly different-looking buttons page to page.
4. **No file over 300 lines.** If it grows past 300, split it. Orchestrators import components — they don't contain JSX logic.
5. **Money is integer paise. Always.** ₹1 = 100 paise. Never floats for currency calculations. Display only converts.
6. **Soft deletes only.** Pharmacy data is compliance data. Hard delete is never acceptable — a batch removed by mistake, or a bill from a customer who's gone, still needs to exist with `deleted_at` set, because a drug-inspector audit or a GST dispute can ask for it years later.
7. **International standard or nothing.** If it wouldn't ship in Linear, Notion, or Stripe — don't ship it here. Concretely: no native browser `confirm()`/`alert()` popups, no unstyled default `<select>`, no "Loading..." text with nothing else — Stripe's dashboard wouldn't ship any of those, so PharmaCare doesn't either.
8. **Zero cognitive load.** Every feature must be completable in the fewest possible clicks. No unnecessary steps, no confirmation modals for reversible actions, no forms asking for data we can infer. If the user has to think — we've failed. Smart defaults, inline edits, auto-save where possible. This is why "Edit Bill" on a paid bill silently opening a fully locked, unexplained screen (Sep 12, 2026) was a real bug, not just a missing message — the button looked clickable and useful with no way to know it wasn't.
9. **No magic strings. No unverified routes. Ever.** Every status value (`'draft'`, `'paid'`, `'parked'`) comes from `constants/domainConstants.js`. Every API call targets a route you have confirmed exists in the backend routers. Writing a raw string like `status='parked'` or calling `/patients` without checking — that is the bug. Fix the root, not the symptom.
10. **Every error notification must say why.** "Failed to save settings" with no cause is a bug, not a valid error state — the user can't fix what they can't see. Every `toast.error(...)` must show the actual field/reason (`error.message`, already normalised by `frontend/src/lib/axios.js`'s interceptor — see `docs/12_ERROR_HANDLING.md`), never a hardcoded generic fallback alone.
11. **Cross-cutting changes ship as one change, not a series of surprises.** A billing rule doesn't live only in billing — it's also read by the GST report, analytics, the H1 register, stock. Before calling a change to one of these domains done, check every linked consumer listed in `docs/08_ARCHITECTURE.md`'s cross-cutting map and update or verify each one in the same change. Found August 22, 2026 the hard way: an MRP/stock/H1 check added to billing's create path didn't reach its own update/finalize path, and the GST report didn't reach sales/purchase returns, until both were checked separately. Ship the whole surface area, not just the entry point you happened to be looking at. **The map is a floor, not a ceiling** — added Sep 12, 2026, direct instruction, after Customers v1 shipped and only got checked for dependencies when asked afterward. The map doesn't cover every module (it says so for Customers/Suppliers/Settings/Users), so consulting it alone can give a false "clear." Every time, also grep broadly for the touched entity/field outside its own module's folder, and check the three consumers easiest to forget because they aren't "the feature" itself: the Audit Log, any Excel/CSV/PDF export, and any *other* page's UI that displays or depends on the same data. See `pharmacare-ship-checklist`'s Step 2 for the full habit; if you walk a module not yet in the map, add it there instead of leaving the next session to repeat the same incomplete check. **Endpoint invariants are cross-cutting too, not just data** — added Sep 16, 2026, direct question ("how did this happen," "why wasn't this re-checked") after the real permissions system and the audit-log helper were each independently found wired into some routers and not others, for months, because nothing re-checked the rest of the app once the infrastructure existed. `docs/08_ARCHITECTURE.md`'s new "Standing endpoint invariants" section (tenant scoping, permission checks, audit logging, `*_paise` typing — the first three now have automated gates: `design-guard.sh` Rules 15-17) is the same-shaped map as the data one above, just for "every mutating endpoint needs X" instead of "this domain's data is also read here." Its meta-rule: the second time an endpoint needs a fix another endpoint already got, that is the trigger to build the automated gate immediately — not a note to revisit once the pattern "proves itself" a third or fourth time. **A multi-step feature's last step is a fresh cross-persona audit of the whole thing, not that step's own tests** — added Sep 28, 2026, direct question ("how did we miss all these") after the 7-step multi-chain build (`docs/26_MULTI_CHAIN_SCOPE.md`) shipped a real cross-store data leak (`scope=chain` summed every pharmacy sharing a `chain_id`, never checking `user_store_roles` — Step 6 caught and fixed the identical bug class in a sibling helper the same week and nobody went back to check whether Step 4/6b's own helper had it too) plus several product gaps (no frontend for a fully-tested backend `stock-transfer reverse` endpoint, "Add Store" silently resetting every Setting with no warning, only 2 of 14 report types chain-aware with no signal of the boundary) — each step was verified against its own scope right after being built and closed; nothing ever re-opened the finished, multi-step feature and walked it fresh as a pharmacist/admin/owner actually would. Per-step correctness is not whole-feature correctness. This is rule 11's own principle applied across time instead of across modules — do it before writing the "✅ all steps built" status line at the top of the feature's scope doc, not after someone else asks.
12. **Test what you build, before calling it done.** Every feature, fix, or enhancement ships with the tests that prove it — pytest for backend, jest for frontend, at the P0/P1/P2 priority its behavior warrants per `docs/11_TESTING.md`. If no test covers the code path you touched, write one in the same change, and run the suite (locally, then CI) before reporting the work finished. "It compiles" and "the doc says it works" are not evidence — a passing test is. Case in point (Sep 14, 2026): a printed thermal receipt silently dropped the pharmacy's custom header text — saved correctly, showed correctly in Settings' own preview, never appeared on the real print — and `PrintReceipt.jsx` had zero test coverage to catch it.
13. **Anything outside these rules needs permission first, explained simply.** If a task can't be done inside an existing pattern in this file or `/docs` — a new library, a new architecture, bypassing a documented rule, a schema change — stop and ask before building it. Explain in plain language what's being proposed and why, no jargon, so a non-engineer can approve or reject it. Only propose modern, cost-effective options, checked against `docs/22_TECH_RADAR.md` — never just the first tool that comes to mind. Done right (Sep 11, 2026): before migrating every stock quantity column from packs to units — a real schema change — two options were laid out in plain language first (switch to units vs. keep packs plus a remainder counter) and the choice was made with Abinash, not assumed.
14. **No assumptions. Verify, every time.** Don't guess what a route returns, what a doc claims, or whether a pattern still holds — check the real code or the real doc first, per the "HOW TO BUILD" order below. If something looks outdated — a doc, a dependency, a convention, an approach that used to be right — flag it explicitly and ask before deviating from it on your own judgment; don't silently route around it and don't silently keep building on it either. These rules are the law until the user changes them, not a default to override when they seem inconvenient or stale. This is the single most-repeated cause of real bugs in this project's own history (see `docs/15_ROADMAP.md`'s RULE MISSES LOG) — e.g. selling 2 loose tablets from a 10-tablet strip silently left stock completely unchanged (Sep 11, 2026) because the code was assumed to already handle sub-pack quantities, never actually tested against one. **A `docs/*_ACCEPTANCE_SPEC.md` "❌ Missing"/"🐛 Broken" row is a claim to verify, not a fact to build from** — added Sep 24, 2026 after trusting one led to starting a second, conflicting implementation of an already-built, already-tested, already-frontend-wired feature (UC-P09) before a router grep caught it. `scripts/check_doc_status_claims.py` catches only the narrow case where the claim itself quotes a contradicting route — it would **not** have caught this one, so grep the relevant router yourself before proposing a design or telling Abinash something doesn't exist.
15. **Think like a product manager, not just an auditor.** A use-case list built only by reading our own code rediscovers what we already built — it can't tell you what's missing. Before calling any section's use-case list complete, benchmark it against what real competitors actually ship: **eVitalRx, Marg ERP, Pharmasoft, Open Healthcare Network (CARE HMIS)** (see `docs/01_PRODUCT.md` §10 for what's known about each — the 4th is a hospital HIS, not a retail-counter product, so weigh its gaps against actual scope, not just feature count). Named/researched features that we don't have are real gaps, not nice-to-haves — call them out explicitly rather than only listing what exists in our code today.
16. **Every loading state is a skeleton, not a spinner or blank screen.** Added August 26, 2026, direct request. Use `TableSkeleton`/`PageSkeleton`/`CardSkeleton`/`InlineLoader` from `@/components/shared`; if none fits a page's actual layout, compose the raw `Skeleton` primitive (`@/components/ui/skeleton`) into a one-off shape — never a hand-rolled `animate-pulse` div, and never `return null`/nothing while data loads. Found the same day: Dashboard hand-rolled its own pulse divs instead of reusing what already existed, and Team's member list rendered nothing at all while loading. `design-guard.sh` Rule 9 catches the hand-rolled case automatically; a missing skeleton entirely isn't auto-detectable the same way, so it's still a manual review point — see the Component audit checklist.

---

## DESIGN SYSTEM — VISUAL AUTHORITY

**Location:** `PharmaCare Design System/` folder in the project root — HTML
previews are the ground truth for visual output; code must match them.
⛔ Before writing ANY component, page, or UI pattern, open this folder
and check — no exceptions. Full table of what each preview governs now
lives in `.claude/rules/design-system.md` (auto-loads when you touch
frontend UI code — moved out Sep 18, 2026 to keep this file lean).

---

## PROJECT SNAPSHOT

**What:** Indian pharmacy management SaaS — billing, inventory, purchases, GST, compliance.
**Stack:** React + Tailwind CSS + Shadcn/UI · Python FastAPI + SQLAlchemy 2.0 async · PostgreSQL
**Auth:** JWT
**Backend port:** 8000 (`uvicorn main:app --host 0.0.0.0 --port 8000 --reload`)
**Frontend env:** No `REACT_APP_BACKEND_URL` needed locally — `craco.config.js` proxies `/api/*` to `localhost:8000` automatically (works whether the browser and backend share a machine or not). Set the env var only when pointing at a different backend (staging, a different port).

> `backend/server.py` (original MongoDB backup) was deleted Sep 21, 2026 —
> confirmed unused (nothing imported it; `ci.yml`'s flake8 step only
> excluded it from linting) and the app has run on PostgreSQL via
> `backend/main.py` since the migration. Do not recreate it.

---

## DOCS INDEX

> All rules, patterns, and decisions live here — one topic per file. Each
> doc's `# Type:` header line says which group it's in; read by what you
> need, not top to bottom: **Reference** (a fact/rule to check), **How-To**
> (steps for a task), **Explanation** (why, so you don't relitigate a
> decided question), or **Living Status** (current state — always re-read
> fresh, never trust memory of it).

### Reference — facts and rules to check against

| # | File | What's inside |
|---|------|--------------|
| 02 | `docs/02_GLOSSARY.md` | All domain terms — MRP, PTR, Schedule H1, paise, FEFO, etc. |
| 05 | `docs/05_DESIGN_SYSTEM.md` | All design tokens, typography, spacing, banned patterns |
| 06 | `docs/06_COMPONENTS.md` | Every shared component — props, usage, anti-patterns |
| 07 | `docs/07_BUSINESS_LOGIC.md` | Billing, stock, GST, H1 register — exact formulas and flows |
| 09 | `docs/09_DATABASE.md` | All 24 tables, columns, indexes, migration rules |
| 10 | `docs/10_API.md` | All endpoints, request/response shapes, error codes |
| 12 | `docs/12_ERROR_HANDLING.md` | All error states, toast rules, retry patterns |
| 14 | `docs/14_SECURITY.md` | Auth patterns, multi-tenancy rules, sensitive data |
| 16 | `docs/16_NAMING_CONVENTIONS.md` | File, component, variable, DB, API naming rules |
| 17 | `docs/17_ACCESSIBILITY.md` | WCAG AA, ARIA, focus, contrast, keyboard nav |
| 18 | `docs/18_ICONOGRAPHY_MOTION.md` | Lucide icons, sizes, stroke, animation durations |
| 19 | `docs/19_PERFORMANCE.md` | Lighthouse targets, lazy loading, pagination, N+1 rules |
| 20 | `docs/20_CODE_QUALITY.md` | ESLint, Prettier, CI pipeline, audit rubric, SOLID/DRY |
| 21 | `docs/21_FEATURES.md`     | Every feature — what it is, why it exists, who uses it, how it works |
| 25 | `docs/25_SUPPORT_FAQ.md`  | Plain-language Q&A per module/sub-module, Intercom-style — for support agents and, later, end users. Source-of-truth rule: every answer traces to real code or another doc, never guessed. |
| 26 | `docs/26_MULTI_CHAIN_SCOPE.md` | Phase 2 multi-store scoping — schema sketch, the switcher-vs-shared-session decision, what does/doesn't change. Scoping only, 🚫 do not build from it without a separate go-ahead. |

### How-To — step-by-step task guides

| # | File | What's inside |
|---|------|--------------|
| 03 | `docs/03_ONBOARDING.md` | Setup steps, project structure, first-change checklist |
| 04 | `docs/04_GIT_WORKFLOW.md` | Branch strategy, commit format, PR template |
| 11 | `docs/11_TESTING.md` | pytest + jest setup, P0/P1/P2 priorities, critical tests |
| 13 | `docs/13_DEPLOYMENT.md` | Env vars, migration commands, pre-deploy checklist |

### Explanation — why things are the way they are

| # | File | What's inside |
|---|------|--------------|
| 01 | `docs/01_PRODUCT.md` | Vision, personas, feature matrix, non-goals |
| 08 | `docs/08_ARCHITECTURE.md` | System design, ADRs, request lifecycle, security rules |
| 22 | `docs/22_TECH_RADAR.md`   | What's modern/cost-efficient per stack layer, sourced externally — check before adopting new infra |
| 27 | `docs/27_PLATFORM_MODULE_MAP.md` | Core vs. Pharmacy vs. EMR split, the open-core product principle, `pharmacy_id` decision |
| 28 | `docs/28_EMR_SCOPE.md` | EMR module scope, persona flows, build order, what is built (appointments, Rx, settings) |
| 29 | `docs/29_BILLING_SCOPE.md` | Patient Billing build plan — one account per patient, each counter bills its own, billing-desk Pending list. Plan only, 🚫 not built until approved. |
| 30 | `docs/30_CORE_PERSON_SCOPE.md` | One shared `people` record for EMR patients + pharmacy customers (hub and spoke, as OHC does) — design, 5 migration steps, consumers to update, phases, decisions. Plan only, 🚫 not built until approved. |
| 31 | `docs/31_CORE_DOCTOR_SCOPE.md` | Doctors as their own records owned by the hospital, mapped to clinics, separate from logins (users) — design, 4 phases, migration, consumers, decisions (OpenMRS-style Provider vs User). Plan only, 🚫 not built until approved. |
| 32 | `docs/32_CLINICS_SCOPE.md` | Organisation → Clinics — create clinics, map doctor profiles to each (login access stays in Team). No schema change, 3 phases, decisions. Plan only, 🚫 not built until approved. |

### Living Status — current state, always re-read fresh

| # | File | What's inside |
|---|------|--------------|
| 15 | `docs/15_ROADMAP.md` | Built / in-progress / planned / Phase 2+ / tech debt |
| 23 | `docs/23_PURCHASES_ACCEPTANCE_SPEC.md` | Purchases + Purchase Returns full use-case spec vs. real code — every UC rated Built/Partial/Missing with evidence. The template for future module acceptance specs. |
| 24 | `docs/24_REPORTS_ACCEPTANCE_SPEC.md` | Reports/GST/Schedule H1/Dashboard full use-case spec vs. real code — same template as 23. The GST report's Sep 12, 2026 hard-crash and credit-sale exclusion bugs are both fixed (live-reverified Sep 24, 2026) — this line itself was stale until then; see the doc's own Executive Summary, not just this one-liner. |

---

## HOW CLAUDE WORKS WITH ABINASH — WORKFLOW AGREEMENT

> Full history and rationale for every rule below (why it was added, what
> broke without it, what changed) moved to `docs/15_ROADMAP.md`'s "HOW
> CLAUDE WORKS WITH ABINASH — FULL HISTORY" section, Sep 18, 2026, per
> Anthropic's documented 200-line CLAUDE.md target. Read it before
> assuming a one-line rule below is the whole story.

- Branch, not main — work on the session's feature branch, never commit to `main`.
- Commit + push automatically as verified checkpoints; the PR merge into `main` is the real confirmation moment.
- `.githooks/pre-commit` + `scripts/design-guard.sh` enforce these rules for real, not just as suggestions.
- A rule/preference stated only in chat doesn't persist — write it into this file or `docs/*.md`, asking before/after if it should become a standing rule.
- A bug that slips past a written rule gets named (which rule, tooling vs. execution gap) in the chat response, fixed, gated automatically where possible, and logged in `docs/15_ROADMAP.md`'s RULE MISSES LOG.
- Docs and commit messages: bullets, not paragraphs.
- Batch fixes before a live-verify pass when several are already queued for the same page; verify immediately only for an isolated, urgent, or high-risk (money/stock/compliance) fix.
- Run the FULL backend/frontend test suite before pushing — never a filtered subset as the last check.
- Chat replies stay under 100 words; code/docs/commit content keeps whatever length the task needs.
- Default to the simpler, standard fix over a flexible one — don't build speculative flexibility. Simple is not the same as a patch: always recommend the best long-term solution first (the one the product ends up with), and name the quick option only as a clearly-labelled stopgap — never lead with a patch.
- Abinash is non-technical — every technical explanation is spelled out step by step, no jargon, no assumed familiarity.
- Explain the "why" in plain terms before building anything, and stop to ask (`AskUserQuestion`) whenever a decision could reasonably go more than one way — a silent judgment call is still an assumption.
- Product manager first, project manager second — state business reasoning before proposing a build list; "done" means walked as one real use case from zero data, not a passing fixture test.
- CI runs on every push to a feature branch, not just PRs — never substitute local checks for it.
- Docs are grouped by type (Reference/How-To/Explanation/Living Status — see each doc's own `# Type:` line), not read top to bottom.
- Every session self-heals its environment via the `SessionStart` hook (`.claude/hooks/session-start.sh`) — no manual restart dance.
- Task-specific skills (`.claude/skills/*`) replace "remember to check the docs" — each auto-triggers on its matching task and points to the exact doc file for that step.
- `npx tsc --noEmit` and `design-guard.sh` are real automated gates (CI + pre-commit), not manual checklist items.
- `main` is a protected branch — every required CI check actually blocks merge, not just informational.
- Every feature ships through one fixed loop: **Research → Build → Test → Review → Feedback → Loop** — a one-line bug fix can skip a full Research pass, but never Test/Review/Feedback.

---

## DEPENDENCY & ENV SAFETY RULES — NEVER BREAK THE APP

Adding uninstalled packages and wrong env values have crashed the app multiple times.
Full steps (install-before-import order, env-file rules) live in
`.claude/rules/dependencies-env.md` (auto-loads when you touch
`package.json`/`requirements.txt`/`.env*`). The two that matter most even
without opening that file: never hand-edit a manifest without running the
real install command first, and never put a placeholder or fake value in
an env file — an empty key is safer than a fake one.

---

## CURRENT STATE — READ THIS FIRST EVERY SESSION

> Moved to where it can't silently drift out of sync with the code (August
> 2026) — this section used to hold ~80 lines of status/blockers/diary
> directly in this always-loaded file; several of those lines went stale
> and sat wrong for months before anyone caught it. That content still
> exists, just relocated to where an update to it is a normal part of
> shipping the feature it describes, not a second thing to remember:

- **Feature status** (what's built, in progress, planned per domain) →
  `docs/15_ROADMAP.md` status tables.
- **Pre-launch blockers** (data-loss/security gaps, deploy checklist) →
  `docs/13_DEPLOYMENT.md` → PRE-LAUNCH BLOCKERS.
- **Local dev setup** (terminal commands, ports, env) →
  `docs/13_DEPLOYMENT.md` → LOCAL SETUP.
- **Known issues / tech debt** → `docs/15_ROADMAP.md` → KNOWN ISSUES / TECH DEBT.

Read those before assuming a feature isn't built or a bug isn't already
known — don't trust a stale memory of this section from an old session.

---

## QUICK-REFERENCE RULES

### HOW TO BUILD — mandatory order, every single feature

> Skipping this order is what caused every filter bug, every 404, every patched fix.
> Enforced by dedicated skills, not just this list — see `.claude/skills/`:
> `pharmacare-design`, `pharmacare-frontend-build`, `pharmacare-backend-build`,
> `pharmacare-database`, `pharmacare-testing`, `pharmacare-deployment`,
> `pharmacare-ship-checklist`. Each auto-triggers on its matching task and
> points to the exact doc for that step — this is the summary only.

1. **Read the DB model first.** (`backend/models/` or `docs/09_DATABASE.md`)
2. **Read the backend router.** Does the route exist, what does it accept/return? (`docs/10_API.md`)
3. **Read domainConstants.js.** Add the status value there first if it's missing.
4. **Then write the frontend.** Connected to reality — not assumptions.

Never write a frontend filter, API call, or status check before completing steps 1–3.

Page-structure snippet, tab-route table, and the full component-audit
checklist now live in `.claude/rules/frontend-pages.md` (auto-loads when
you touch a page or shared component).

### Stale docs (do not update, do not trust)
`PHARMACARE_RULES.md` · `PHARMACARE_DESIGN_SKILL.md` · `PHARMACARE_DESIGN_BRIEF.md` · `CONTEXT.md` · `PROGRESS.md` · `DECISIONS.md` · `TECH_SPEC.md` · `PHARMACARE_DATABASE_SCHEMA.md`

### Deleted files (do not recreate)
- `memory/PRD.md` — mentioned MongoDB (replaced by PostgreSQL) and teal as primary colour (replaced by brand blue #4682B4). Deleted April 19, 2026. Source of truth is `docs/` folder.
