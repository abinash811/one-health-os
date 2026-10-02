#!/usr/bin/env python3
"""check_chain_scope_safety.py — fails if a backend router builds a list of
pharmacy_ids from raw chain membership (`.chain_id ==` / `.chain_id.in_(`)
without going through the one sanctioned, grant-checked helper.

Why this exists: found Sep 28, 2026 (docs/15_ROADMAP.md RULE MISSES LOG) that
GET /analytics/dashboard, GET /analytics/purchases, and GET /reports/gst's
`?scope=chain` toggle summed every pharmacy sharing the caller's chain_id,
full stop — it never checked whether the caller actually held a
user_store_roles grant at each of those other stores. A user whose home
store merely happened to sit in a multi-store chain could pull every other
branch's revenue/GST/purchase totals under scope=chain, even with zero grant
there. This is the exact class of bug resolve_store_override /
resolve_store_override_for_write (routers/auth_helpers.py) were built to
prevent for WRITEs — it was never applied to this read-rollup path, because
the read path built its own multi-pharmacy_id list inline instead of going
through a shared, checked helper.

routers/auth_helpers.py's resolve_chain_scope_pids() is now the one
sanctioned way to turn a scope=store|chain toggle into a pharmacy_id list —
it intersects chain membership with the caller's real user_store_roles
grants. This script can't tell "safe because it's the canonical helper
itself" apart from "a new ad-hoc reimplementation" by itself, so it uses a
narrow, deliberately conservative heuristic:

  Flag any line in backend/routers/*.py referencing `.chain_id ==` or
  `.chain_id.in_(` in a query filter, UNLESS the file is auth_helpers.py
  (where the canonical helper lives) or chains.py (which legitimately lists
  every store in a chain for the Settings "Stores" tab / Team page picker —
  a different, non-financial concern: showing what stores EXIST in the
  chain, not summing data across them).

A deliberate, reviewed exception elsewhere is marked with a trailing
`# chain-scope-safe: <reason>` comment, same precedent as
check_tenant_isolation.py's `# tenant-safe:` marker.

Usage: python3 scripts/check_chain_scope_safety.py
Exit 0 = every chain_id-based pharmacy list goes through the canonical
         helper or is explicitly justified.
Exit 1 = at least one raw chain_id query found outside the sanctioned files
         (prints file:line).
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTERS_DIR = REPO_ROOT / "backend" / "routers"
# Platform modules (docs/27) keep their own routers under backend/modules/<name>/routers/ —
# they get the same endpoint-safety gates as the core routers (added Oct 2, 2026 with EMR).
MODULE_ROUTERS_GLOB = (REPO_ROOT / "backend" / "modules").glob("*/routers/*.py")

# auth_helpers.py defines resolve_chain_scope_pids() itself — the one
# sanctioned place a chain_id membership query is built, always intersected
# with the caller's real user_store_roles grants. chains.py legitimately
# lists every store in a chain (Settings "Stores" tab, Team page store
# picker) — a membership listing, not a financial-data rollup, so raw
# chain_id membership is the correct query there, not a leak.
EXEMPT_FILES = {"auth_helpers.py", "chains.py"}

CHAIN_ID_QUERY_RE = re.compile(r"\.chain_id\s*(==|\.in_\()")
SAFE_MARKER = "# chain-scope-safe:"


def check_file(path: Path) -> list[str]:
    violations = []
    lines = path.read_text().split("\n")
    for i, line in enumerate(lines, start=1):
        if not CHAIN_ID_QUERY_RE.search(line):
            continue
        if SAFE_MARKER in line:
            continue
        violations.append(
            f"{path.relative_to(REPO_ROOT)}:{i}: raw .chain_id query outside "
            f"resolve_chain_scope_pids() — {line.strip()}")
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
        print("Chain-scope safety check: OK — every pharmacy_id list built "
              "from chain membership goes through resolve_chain_scope_pids() "
              "(or a reviewed # chain-scope-safe: comment).")
        return 0

    print("Chain-scope safety check: FAILED")
    print()
    print("These queries build a multi-pharmacy list from raw .chain_id")
    print("membership instead of routers/auth_helpers.py's")
    print("resolve_chain_scope_pids() — the exact gap found Sep 28, 2026")
    print("(docs/15_ROADMAP.md RULE MISSES LOG) that let scope=chain leak")
    print("other branches' revenue/GST/purchase data to a user with zero")
    print("grant there. Use resolve_chain_scope_pids(current_user, scope, db)")
    print("instead, or mark a reviewed exception with a trailing")
    print("`# chain-scope-safe: <reason>` comment.")
    print()
    for v in all_violations:
        print(f"  {v}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
