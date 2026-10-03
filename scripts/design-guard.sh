#!/usr/bin/env bash
# design-guard.sh — PharmaCare design system enforcement
# Runs in CI and pre-commit. Exits 1 if any violation found.
# Rules mirror CLAUDE.md component audit checklist.
#
# Usage: bash scripts/design-guard.sh
# Make executable first: chmod +x scripts/design-guard.sh

set -euo pipefail

FRONTEND="frontend/src/pages"
SHARED="frontend/src/components"
BACKEND_ROUTERS="backend/routers"
ERRORS=0

red()   { echo -e "\033[0;31m✗ $*\033[0m"; }
green() { echo -e "\033[0;32m✓ $*\033[0m"; }
warn()  { echo -e "\033[0;33m  $*\033[0m"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PharmaCare Design Guard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Rule 1: No raw <button> tags in pages (AppButton only) ───────────────
# Excludes: WelcomeCard navigational tiles (intentional exception, documented)
# The BillingHeader split-button exclusion was removed Sep 6, 2026 once
# that control was migrated to AppButton — see CLAUDE.md RULE MISSES LOG.
RAW_BUTTONS=$(grep -rn "<button" "$FRONTEND" --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
  | grep -v "WelcomeCard" \
  | grep -v "// raw button" \
  | wc -l | tr -d ' ' || true)

if [ "$RAW_BUTTONS" -gt "0" ]; then
  red "Rule 1 FAIL: $RAW_BUTTONS raw <button> tag(s) found in pages/"
  grep -rn "<button" "$FRONTEND" --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
    | grep -v "WelcomeCard" \
    | grep -v "// raw button" \
    | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 1 PASS: No raw <button> tags in pages"
fi

# ── Rule 2: No hardcoded hex colors in className ────────────────────────
HEX_COLORS=$(grep -rn "className=.*#[0-9a-fA-F]\{3,6\}" "$FRONTEND" "$SHARED" \
  --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
  | grep -v "AuthPage" \
  | wc -l | tr -d ' ' || true)

if [ "$HEX_COLORS" -gt "0" ]; then
  red "Rule 2 FAIL: $HEX_COLORS hardcoded hex color(s) in className"
  grep -rn "className=.*#[0-9a-fA-F]\{3,6\}" "$FRONTEND" "$SHARED" \
    --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
    | grep -v "AuthPage" \
    | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 2 PASS: No hardcoded hex in className"
fi

# ── Rule 3: No hover:bg-[#...] patterns ─────────────────────────────────
HOVER_HEX=$(grep -rn "hover:bg-\[#" "$FRONTEND" "$SHARED" \
  --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" | wc -l | tr -d ' ' || true)

if [ "$HOVER_HEX" -gt "0" ]; then
  red "Rule 3 FAIL: $HOVER_HEX hover:bg-[#...] pattern(s) found"
  grep -rn "hover:bg-\[#" "$FRONTEND" "$SHARED" --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
    | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 3 PASS: No hover:bg-[#...] patterns"
fi

# ── Rule 4: No files over 300 lines in pages/ ────────────────────────────
LONG_FILES=0
while IFS= read -r -d '' file; do
  lines=$(wc -l < "$file")
  if [ "$lines" -gt 300 ]; then
    red "Rule 4 FAIL: $file has $lines lines (max 300)"
    LONG_FILES=$((LONG_FILES + 1))
  fi
done < <(find "$FRONTEND" \( -name "*.jsx" -o -name "*.js" -o -name "*.tsx" -o -name "*.ts" \) | grep -v node_modules | tr '\n' '\0')

if [ "$LONG_FILES" -eq "0" ]; then
  green "Rule 4 PASS: All files under 300 lines"
else
  ERRORS=$((ERRORS + LONG_FILES))
fi

# ── Rule 5: No Shadcn <Button> imported in pages ─────────────────────────
SHADCN_BUTTON=$(grep -rn "from '@/components/ui/button'" "$FRONTEND" \
  --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" | wc -l | tr -d ' ' || true)

if [ "$SHADCN_BUTTON" -gt "0" ]; then
  red "Rule 5 FAIL: $SHADCN_BUTTON page(s) import directly from ui/button — use AppButton from shared"
  grep -rn "from '@/components/ui/button'" "$FRONTEND" \
    --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
    | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 5 PASS: No direct ui/button imports in pages"
fi

# ── Rule 6: No new .jsx files — use .tsx ─────────────────────────────────
NEW_JSX=$(git diff --name-only --cached --diff-filter=A 2>/dev/null | grep "\.jsx$" | grep -v node_modules | wc -l | tr -d ' ' || true)

if [ "$NEW_JSX" -gt "0" ]; then
  red "Rule 6 FAIL: $NEW_JSX new .jsx file(s) staged — use .tsx instead"
  git diff --name-only --cached --diff-filter=A 2>/dev/null | grep "\.jsx$" | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 6 PASS: No new .jsx files staged"
fi

# ── Rule 7: No hand-rolled "More menu" dropdowns — use <MoreMenu> ───────
# This exact pattern (top-full mt-1 + shadow-xl popover) was independently
# duplicated across 3 pages before being extracted into components/shared/
# MoreMenu.tsx — one page even shipped without a working close-on-outside-
# click. Catch the next duplicate before it's written, not after.
MOREMENU_DUPES=$(grep -rln "top-full mt-1" "$FRONTEND" "$SHARED" \
  --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
  | grep -v "MoreMenu.tsx" || true)

if [ -n "$MOREMENU_DUPES" ]; then
  COUNT=$(echo "$MOREMENU_DUPES" | wc -l | tr -d ' ')
  red "Rule 7 FAIL: $COUNT file(s) hand-roll a 'More menu'-shaped dropdown"
  echo "$MOREMENU_DUPES" | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 7 PASS: No duplicated More-menu dropdowns"
fi

# ── Rule 8: Design tokens must agree between tailwind.config.js and the
# design system reference (colors_and_type.css) ──────────────────────────
# Motion tokens disagreed between these two files for months before being
# caught by chance, not by any automated check — this is what would have
# caught it on day one instead.
if python3 scripts/design_token_sync_check.py > /tmp/token_sync_output 2>&1; then
  green "Rule 8 PASS: Design tokens in sync"
else
  red "Rule 8 FAIL: design tokens disagree between tailwind.config.js and colors_and_type.css"
  cat /tmp/token_sync_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 9: No hand-rolled loading skeletons — use Skeleton/TableSkeleton/
# PageSkeleton/CardSkeleton/InlineLoader from shared ─────────────────────
# Found Aug 26, 2026: Dashboard hand-rolled its own animate-pulse divs
# instead of reusing the shared Skeleton system that already existed —
# same class of duplication Rule 7 catches for "More menu" dropdowns.
SKELETON_DUPES=$(grep -rln "animate-pulse" "$FRONTEND" "$SHARED" \
  --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" \
  | grep -v "ui/skeleton.tsx" || true)

if [ -n "$SKELETON_DUPES" ]; then
  COUNT=$(echo "$SKELETON_DUPES" | wc -l | tr -d ' ')
  red "Rule 9 FAIL: $COUNT file(s) hand-roll a loading skeleton instead of using the shared Skeleton system"
  echo "$SKELETON_DUPES" | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 9 PASS: No hand-rolled skeleton loaders"
fi

# ── Rule 10: TypeScript must type-check clean ────────────────────────────
# Was a checklist item nobody ran ("manual — not yet wired into
# design-guard.sh"). Closed Sep 5, 2026 as part of the enforcement-layer
# setup pass -- a type error is exactly the kind of thing a human forgets
# to check and a script never does.
if (cd "$(dirname "$0")/../frontend" && npx tsc --noEmit > /tmp/tsc_output 2>&1); then
  green "Rule 10 PASS: TypeScript type-checks clean"
else
  red "Rule 10 FAIL: TypeScript errors found"
  cat /tmp/tsc_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 11 (warn-only): clickable <div>/<tr> should be keyboard-accessible ──
# Found 9 real instances Sep 7, 2026 (docs/17_ACCESSIBILITY.md already
# documented this rule — it just wasn't enforced anywhere, so it got
# violated anyway). Tried this as a hard-fail line-proximity check first;
# reverted to warn-only after it flagged ~30 false positives — a container
# <div> whose child <button> has its own onClick a line or two later reads
# identically to a real violation from grep's vantage point, and there's no
# way to tell them apart without real JSX parsing. Loud-but-wrong would
# train people to ignore this tool, so: advisory, not blocking.
# Superseded Sep 8, 2026 by `eslint-plugin-jsx-a11y` (real AST parsing, wired
# into eslint.config.js — see docs/11_TESTING.md CI STATUS), which catches
# this exact class reliably via `npm run lint`, with none of this grep
# check's false positives. Left running here too since it's free and
# harmless, but `npm run lint` is now the real gate for this class of bug.
CLICKABLE_NOTE=0
for tag in div tr; do
  while IFS=: read -r file lineno _; do
    [ -z "$file" ] && continue
    window=$(sed -n "${lineno},$((lineno + 5))p" "$file")
    if echo "$window" | grep -q "onClick=" && ! echo "$window" | grep -qE "tabIndex|role=|stopPropagation"; then
      CLICKABLE_NOTE=$((CLICKABLE_NOTE + 1))
    fi
  done < <(grep -rn "<${tag}\b" "$FRONTEND" "$SHARED" --include="*.jsx" --include="*.tsx" 2>/dev/null | grep -v "test\|InventorySearch/index.jsx")
done
if [ "$CLICKABLE_NOTE" -gt "0" ]; then
  warn "Rule 11 NOTE: $CLICKABLE_NOTE <div>/<tr> near an onClick with no role/tabIndex nearby — most are containers whose real button child is fine; manually verify any that are themselves the clickable element (see docs/17_ACCESSIBILITY.md)"
fi

# ── Rule 12 (warn-only): truncated dynamic content should keep a title ──
# Not a hard fail — many truncate usages are fixed short labels that never
# need one (a column header, a static button caption), and grep can't tell
# those apart from a truncated real name/email reliably. This is a nudge to
# check manually, same spirit as Rule 7's "trivially evaded" caveat.
TRUNCATE_NO_TITLE=$(grep -rn "truncate" "$FRONTEND" "$SHARED" --include="*.jsx" --include="*.tsx" 2>/dev/null \
  | grep -v "title=\|test\|line-clamp" | wc -l | tr -d ' ' || true)
if [ "$TRUNCATE_NO_TITLE" -gt "0" ]; then
  warn "Rule 12 NOTE: $TRUNCATE_NO_TITLE truncate usage(s) without a title= on the same line — verify each is a fixed label, not real data (see docs/05_DESIGN_SYSTEM.md's Content Truncation rule)"
fi

# ── Rule 13: Backend by-ID lookups must be pharmacy-scoped ───────────────
# Found Sep 12, 2026: nearly every "get/update/delete by id" endpoint did
# `select(Model).where(Model.id == id)` with no pharmacy_id check at all —
# proved live, a freshly-registered pharmacy could read AND modify another
# pharmacy's supplier via GET/PUT /suppliers/{id}. This class of bug had
# already been found and fixed once before (the bill-PDF endpoint) but was
# never generalized into a shared helper or a check, so it silently
# reappeared in ~20 sibling endpoints. See docs/15_ROADMAP.md RULE MISSES
# LOG and routers/auth_helpers.py's get_owned_or_404().
if python3 scripts/check_tenant_isolation.py > /tmp/tenant_isolation_output 2>&1; then
  green "Rule 13 PASS: All backend by-ID lookups are pharmacy-scoped"
else
  red "Rule 13 FAIL: unscoped by-ID lookup(s) found in $BACKEND_ROUTERS"
  cat /tmp/tenant_isolation_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 14: Caught errors must show the real reason, not a fixed string ──
# Found Sep 12, 2026 (CLAUDE.md rule 10): useReports.js/useDashboard.js
# both had toast.error('Failed to load...') inside a catch block, hiding
# error.message entirely. A repo-wide sweep with this same checker then
# found the identical pattern already live in App.js's OAuth callback,
# AuditLog.jsx, ScheduleH1Register.jsx, and 3 of 4 near-identical billing
# actions in useBillActions.js (the 4th, saveBill, already did it right —
# copy-paste drift lost it in the other three). See docs/15_ROADMAP.md
# RULE MISSES LOG.
if python3 scripts/check_error_messages.py > /tmp/error_messages_output 2>&1; then
  green "Rule 14 PASS: Every caught-error toast shows the real reason"
else
  red "Rule 14 FAIL: hardcoded-only error toast(s) found in $FRONTEND"
  cat /tmp/error_messages_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 15: Mutating backend endpoints must have a permission check ────
# Found Sep 2026: the real permissions system (roles table, has_permission())
# was wired into Purchases/Purchase Returns only — Billing, Inventory,
# Customers, Reports, Settings stayed fully open to any authenticated user
# for months, because each module's review checked that module's own logic,
# never "does this module's writes need a gate like Purchases got." See
# docs/15_ROADMAP.md RULE MISSES LOG.
if python3 scripts/check_permission_coverage.py > /tmp/permission_coverage_output 2>&1; then
  green "Rule 15 PASS: Every mutating endpoint has a permission check"
else
  red "Rule 15 FAIL: unguarded mutating endpoint(s) found in $BACKEND_ROUTERS"
  cat /tmp/permission_coverage_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 16: Mutating backend endpoints must write an audit trail ───────
# Found Sep 2026: sales_returns.py shipped with zero _record_audit() calls
# for months, and customers.py had none until a later product-review pass
# found it as an unchecked dependency. An audit gap doesn't break a
# feature's own tests — it just leaves no record of who did what. See
# docs/15_ROADMAP.md RULE MISSES LOG.
if python3 scripts/check_audit_log_coverage.py > /tmp/audit_log_coverage_output 2>&1; then
  green "Rule 16 PASS: Every mutating endpoint writes an audit trail"
else
  red "Rule 16 FAIL: silently-unaudited mutating endpoint(s) found in $BACKEND_ROUTERS"
  cat /tmp/audit_log_coverage_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 17: Every *_paise column must be Integer ───────────────────────
# CLAUDE.md Manifesto rule 5 ("money is integer paise, always") had no
# automated check behind it — the same "manual habit, not tooling" gap
# already closed for tenant isolation, permissions, and audit logging.
if python3 scripts/check_money_paise_columns.py > /tmp/money_paise_output 2>&1; then
  green "Rule 17 PASS: Every *_paise column is Integer"
else
  red "Rule 17 FAIL: non-Integer *_paise column(s) found in backend/models"
  cat /tmp/money_paise_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 18: No .js/.ts or .jsx/.tsx twin-name duplicates ───────────────
# Found Sep 19, 2026 (2nd occurrence of the api.js/api.ts class already
# fixed once, Sep 16, 2026 — see docs/15_ROADMAP.md RULE MISSES LOG):
# react-scripts/webpack resolves an extensionless import to .js/.jsx
# BEFORE .ts/.tsx (see paths.moduleFileExtensions), so whenever both
# twins exist, the .ts/.tsx one is silently dead — never bundled, never
# executed, no matter how correct or how recently edited. 9 such pairs
# were found this way (lib/axios, hooks/useApiCall, hooks/useDebounce,
# hooks/usePagination, constants/pharmacy, utils/gst, utils/validation,
# utils/currency, utils/dates) — one of them (lib/axios.ts) had silently
# regressed a real fix (the wrong-password-shouldn't-hard-redirect fix)
# that only the live .js twin actually had. Per Manifesto rule 11's
# meta-rule, a 2nd occurrence of the same class gets an automated gate
# in the same change, not another one-off fix.
DUPLICATE_TWINS=""
while IFS= read -r ts_file; do
  js_file="${ts_file%.ts}.js"
  jsx_file="${ts_file%.ts}.jsx"
  [ -f "$js_file" ] && DUPLICATE_TWINS="$DUPLICATE_TWINS$ts_file + $js_file"$'\n'
  [ -f "$jsx_file" ] && DUPLICATE_TWINS="$DUPLICATE_TWINS$ts_file + $jsx_file"$'\n'
done < <(find frontend/src -name "*.ts" -not -name "*.d.ts" -not -path "*/node_modules/*")
while IFS= read -r tsx_file; do
  js_file="${tsx_file%.tsx}.js"
  jsx_file="${tsx_file%.tsx}.jsx"
  [ -f "$js_file" ] && DUPLICATE_TWINS="$DUPLICATE_TWINS$tsx_file + $js_file"$'\n'
  [ -f "$jsx_file" ] && DUPLICATE_TWINS="$DUPLICATE_TWINS$tsx_file + $jsx_file"$'\n'
done < <(find frontend/src -name "*.tsx" -not -path "*/node_modules/*")

if [ -n "$DUPLICATE_TWINS" ]; then
  COUNT=$(echo -n "$DUPLICATE_TWINS" | grep -c "+" || true)
  red "Rule 18 FAIL: $COUNT same-basename .js/.ts (or .jsx/.tsx) pair(s) found — the .ts/.tsx side is silently dead code"
  echo "$DUPLICATE_TWINS" | while read -r line; do [ -n "$line" ] && warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 18 PASS: No .js/.ts or .jsx/.tsx twin-name duplicates"
fi

# ── Rule 19: No `.toISOString().split('T')[0]` date-to-string conversion ──
# Found Sep 19, 2026: toISOString() converts to UTC before formatting, so
# for any timezone AHEAD of UTC — India, UTC+5:30, this product's entire
# market — a locally-picked date silently shifts back a day (a date-picker
# selection is always local midnight, which is always the previous day
# once converted to UTC when the local zone is ahead of it). This was
# copy-pasted into ~20 real call sites across the app — GST Report's own
# date range, every report/list date filter, Day-End Closing (wrong day
# closed every time), Schedule H1 Register (a legal register), and real
# stored data (Purchase's purchase_date/due_date, which drives GST period
# attribution) — before being fixed the same day. utils/dates.js's
# toISODate()/today() already existed as the correct, canonical helper
# (reads the Date object's local year/month/day via date-fns' format(),
# never converts timezone) — almost nothing used it.
ISO_SPLIT_HITS=$(grep -rn "toISOString().split('T')\[0\]\|toISOString().slice(0, *10)" "$FRONTEND" "$SHARED" frontend/src/utils frontend/src/hooks \
  --include="*.jsx" --include="*.js" --include="*.tsx" --include="*.ts" 2>/dev/null \
  | grep -v "^frontend/src/utils/dates.js" \
  | grep -vE ':\s*(//|\*|/\*)' || true)

if [ -n "$ISO_SPLIT_HITS" ]; then
  COUNT=$(echo "$ISO_SPLIT_HITS" | wc -l | tr -d ' ')
  red "Rule 19 FAIL: $COUNT use(s) of toISOString() to build a date-only string — use toISODate()/today() from @/utils/dates instead (UTC conversion silently shifts the date for any timezone ahead of UTC, incl. India)"
  echo "$ISO_SPLIT_HITS" | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
else
  green "Rule 19 PASS: No toISOString()-based date-only conversions outside utils/dates.js"
fi

# ── Rule 20 (warn-only): acceptance-spec docs claiming a route is missing ──
# that already has a real handler — see docs/15_ROADMAP.md RULE MISSES LOG,
# Sep 24, 2026 (UC-P09/UC-P31). Narrow by design (only fires when the doc's
# own "Missing"/"Broken" text quotes the contradicting route) — see
# scripts/check_doc_status_claims.py's own docstring for what it can't catch.
DOC_CLAIM_OUTPUT=$(python3 scripts/check_doc_status_claims.py 2>&1 || true)
if echo "$DOC_CLAIM_OUTPUT" | grep -q "possible stale"; then
  warn "Rule 20 NOTE: $(echo "$DOC_CLAIM_OUTPUT" | grep -c '^  ') acceptance-spec row(s) may be stale — see scripts/check_doc_status_claims.py output"
  echo "$DOC_CLAIM_OUTPUT" | tail -n +2 | while read -r line; do warn "$line"; done
else
  green "Rule 20 PASS: No quoted-route acceptance-spec claims contradicted by real code"
fi

# ── Rule 21: Chain-scope pharmacy_id lists must go through the checked
# canonical helper, never raw .chain_id membership ─────────────────────
# Found Sep 28, 2026: GET /analytics/dashboard, GET /analytics/purchases,
# and GET /reports/gst's scope=chain toggle summed every pharmacy sharing
# the caller's chain_id, full stop — never checked user_store_roles, so a
# user whose home store merely sat in a chain could see other branches'
# revenue/GST/purchase totals with zero grant there. See docs/15_ROADMAP.md
# RULE MISSES LOG and routers/auth_helpers.py's resolve_chain_scope_pids().
if python3 scripts/check_chain_scope_safety.py > /tmp/chain_scope_safety_output 2>&1; then
  green "Rule 21 PASS: Chain-scope pharmacy lists go through the grant-checked helper"
else
  red "Rule 21 FAIL: raw chain_id-based pharmacy list(s) found in $BACKEND_ROUTERS"
  cat /tmp/chain_scope_safety_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 22: DB session must be the shared scope="function" DbSession ──────
# Found Oct 2, 2026: a bare Depends(get_db) makes FastAPI (0.118+) send the response BEFORE
# the session commits — clients were told "saved" before the data was committed, causing
# random read-after-write failures and hiding any commit error. See deps.py's DbSession and
# docs/15_ROADMAP.md RULE MISSES LOG.
if python3 scripts/check_db_session_scope.py > /tmp/db_session_scope_output 2>&1; then
  green "Rule 22 PASS: Every endpoint uses the shared DbSession (commit finishes before the response)"
else
  red "Rule 22 FAIL: bare Depends(get_db) found — use DbSession from deps.py"
  cat /tmp/db_session_scope_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 23: DEFAULT_ROLES may only grant permissions that exist ───────────
# Found Oct 3, 2026 (B5 audit): stored role permissions drifted into three generations because new
# permissions were added to constants.py with no check and no data migration. A typo'd id grants nothing.
if python3 scripts/check_default_roles.py > /tmp/default_roles_output 2>&1; then
  green "Rule 23 PASS: Every default-role permission is a defined permission"
else
  red "Rule 23 FAIL: DEFAULT_ROLES / ALL_PERMISSIONS inconsistent"
  cat /tmp/default_roles_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Rule 24: every place that creates a User also writes its store-access row ──────────
# Found Oct 3, 2026: seed_admin.py skipped user_store_roles, so the store switcher and clinic pickers were
# empty for the first admin. See scripts/check_user_creation_paths.py.
if python3 scripts/check_user_creation_paths.py > /tmp/user_creation_output 2>&1; then
  green "Rule 24 PASS: Every user-creation path writes its store-access row"
else
  red "Rule 24 FAIL: a User is created without sync_user_store_role"
  cat /tmp/user_creation_output | while read -r line; do warn "$line"; done
  ERRORS=$((ERRORS + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$ERRORS" -eq "0" ]; then
  echo -e "\033[0;32m  ✓ All checks passed\033[0m"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 0
else
  echo -e "\033[0;31m  ✗ $ERRORS violation(s) found — fix before merging\033[0m"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 1
fi
