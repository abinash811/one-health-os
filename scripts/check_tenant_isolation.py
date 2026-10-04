#!/usr/bin/env python3
"""check_tenant_isolation.py — fails if a backend router looks up a
pharmacy-owned row by primary key without scoping the query to the
caller's own pharmacy_id.

Why this exists: found Sep 12, 2026 that nearly every "get/update/delete
by id" endpoint in the app did `select(Model).where(Model.id == id)` with
no pharmacy_id check at all. Proved live: a freshly-registered, completely
separate pharmacy could read AND modify another pharmacy's supplier via
GET/PUT /suppliers/{id}. The bill-PDF endpoint had this exact fix applied
once before (a real, found cross-tenant leak) but it was never generalized
into a shared helper or an automated check — the same bug quietly
reappeared in ~20 sibling endpoints across suppliers.py, customers.py,
inventory.py, batches.py, billing.py, purchases.py, purchase_returns.py,
sales_returns.py, users.py, and settings.py, all fixed in the same change
this script shipped with. See docs/15_ROADMAP.md's RULE MISSES LOG.

routers/auth_helpers.py's get_owned_or_404() is now the one sanctioned way
to do this lookup — it always scopes by pharmacy_id and always returns 404
(never 403) for a row that exists but belongs to someone else. This script
can't tell "safe because it's already scoped" apart from "vulnerable" by
itself, so it uses a narrow, deliberately conservative heuristic:

  Flag any `select(Model).where(...)` statement in backend/routers/*.py
  that contains a bare `Model.id ==` / `SomeORM.id ==` primary-key
  equality check, UNLESS the same statement also mentions `pharmacy_id`.

This will have some false positives for lookups that are safe because
they key off a value already derived from a properly-scoped parent row
(e.g. batches.py resolving a Product from a StockBatch it already fetched
with get_owned_or_404) — those are marked with a trailing
`# tenant-safe: <reason>` comment, which this script treats as a
deliberate, reviewed exception rather than silently allowing every such
pattern through.

Usage: python3 scripts/check_tenant_isolation.py
Exit 0 = every by-ID lookup is scoped or explicitly justified.
Exit 1 = at least one unscoped lookup found (prints file:line).
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTERS_DIR = REPO_ROOT / "backend" / "routers"
# Platform modules (docs/27) keep their own routers under backend/modules/<name>/routers/ —
# they get the same endpoint-safety gates as the core routers (added Oct 2, 2026 with EMR).
MODULE_ROUTERS_GLOB = (REPO_ROOT / "backend" / "modules").glob("*/routers/*.py")

# auth_helpers.py defines get_owned_or_404 itself (its own internal query is
# the one sanctioned unscoped-looking pattern used correctly — it takes
# pharmacy_id as an explicit parameter and always applies it) and also
# contains the get_current_user JWT-decode lookup, which is scoped by the
# token's own subject, not attacker-supplied input. Both are exempt by
# construction, not by loophole — nothing else should import this pattern
# from anywhere else.
EXEMPT_FILES = {"auth_helpers.py"}

ID_EQ_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.id\s*==")
SAFE_MARKER = "# tenant-safe:"


def _find_matching_close(source: str, open_idx: int) -> int | None:
    depth = 0
    for i in range(open_idx, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def _extend_through_chain(source: str, open_idx: int) -> int | None:
    """`select(X)` is almost never the whole query — real code chains
    `.where(...)`, `.order_by(...)`, `.limit(...)` etc. Stopping at the
    first balanced close (just `select(X)`) would miss the .where() clause
    entirely, which is exactly where the pharmacy_id check (or its
    absence) actually lives."""
    n = len(source)
    i = open_idx
    while True:
        end = _find_matching_close(source, i)
        if end is None:
            return None
        j = end + 1
        while j < n and source[j] in " \t\n":
            j += 1
        if j < n and source[j] == ".":
            k = j + 1
            while k < n and (source[k].isalnum() or source[k] == "_"):
                k += 1
            while k < n and source[k] in " \t\n":
                k += 1
            if k < n and source[k] == "(":
                i = k
                continue
        return end


def find_statements(source: str) -> list[tuple[int, str]]:
    """Split source into (start_line, statement_text) chunks, one per
    `select(...)` call plus every chained `.where(...)`/`.order_by(...)`/
    etc. that follows it. Good enough for this codebase's formatting — it
    doesn't need to be a real Python parser, just consistent enough not to
    miss a real violation."""
    statements = []
    for m in re.finditer(r"\bselect\(", source):
        start = m.start()
        open_idx = m.end() - 1  # position of the opening '('
        end = _extend_through_chain(source, open_idx)
        if end is None:
            continue
        stmt = source[start:end + 1]
        line_no = source.count("\n", 0, start) + 1
        statements.append((line_no, stmt))
    return statements


def check_file(path: Path) -> list[str]:
    violations = []
    source = path.read_text()
    lines = source.split("\n")

    for line_no, stmt in find_statements(source):
        if not ID_EQ_RE.search(stmt):
            continue
        # `clinic_id` is the tenant key of the EMR / patient-billing tables (docs/32 P2b).
        if "pharmacy_id" in stmt or "clinic_id" in stmt:
            continue
        # A "# tenant-safe: ..." comment anywhere within the statement's own
        # span, or on the line immediately before it (a long statement often
        # needs the comment moved above to stay under the line-length
        # limit), marks a reviewed, deliberate exception.
        span_line_count = stmt.count("\n") + 1
        first_span_line = max(1, line_no - 1)
        span_text = "\n".join(lines[first_span_line - 1: line_no - 1 + span_line_count])
        if SAFE_MARKER in span_text:
            continue
        snippet = " ".join(stmt.split())[:100]
        violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {snippet}")

    return violations


def main() -> int:
    if not ROUTERS_DIR.exists():
        print(f"SKIP: {ROUTERS_DIR} not found")
        return 0

    all_violations = []
    for path in sorted(list(ROUTERS_DIR.glob("*.py")) + list(MODULE_ROUTERS_GLOB)):
        if path.name in EXEMPT_FILES:
            continue
        all_violations.extend(check_file(path))

    if not all_violations:
        print("Tenant isolation check: OK — every by-ID lookup is pharmacy-scoped "
              "(or explicitly marked # tenant-safe:).")
        return 0

    print("Tenant isolation check: FAILED")
    print()
    print("These queries look up a row by primary key without scoping to the")
    print("caller's own pharmacy_id — the exact cross-tenant IDOR class found and")
    print("fixed Sep 12, 2026 (docs/15_ROADMAP.md RULE MISSES LOG). Use")
    print("get_owned_or_404() from routers/auth_helpers.py instead, or add")
    print("`pharmacy_id` to the same query if there's a reason not to. If this is")
    print("a false positive (the ID is already derived from a properly-scoped")
    print("parent row), mark it with a trailing `# tenant-safe: <reason>` comment.")
    print()
    for v in all_violations:
        print(f"  {v}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
