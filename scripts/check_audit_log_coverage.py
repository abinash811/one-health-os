#!/usr/bin/env python3
"""check_audit_log_coverage.py — fails if a mutating backend endpoint
(POST/PUT/PATCH/DELETE) writes no audit trail at all.

Why this exists: docs/15_ROADMAP.md's RULE MISSES LOG shows this exact gap
recurring on its own, independent of the permission-check gap
(check_permission_coverage.py) it's modeled on: sales_returns.py shipped
with zero `_record_audit()` calls anywhere for months (found Sep 15, 2026,
"the module's single most important promise... completely false"), and
customers.py had zero audit rows for any create/update/delete until the
Sep 12, 2026 Customers v1 pass found it as a dependency nobody had checked.
Every time this shipped, the module's own business logic looked and tested
correct — an audit gap doesn't break a feature, it just leaves no record of
who did what, which is exactly the kind of gap nothing but a dedicated
check ever catches.

Flags: any POST/PUT/PATCH/DELETE endpoint function in backend/routers/*.py
whose body contains no call to `_record_audit(` (the shared per-router
audit-log helper) or `_record_movement(` (batches.py's equivalent
StockMovement ledger, the sanctioned audit trail for a quantity change) —
and no `# audit-exempt: <reason>` comment anywhere in its body.

A `# audit-exempt: <reason>` comment marks a deliberate, reviewed
exception (e.g. a read-adjacent action, or a mutation intentionally not
worth its own audit row) — same precedent as check_tenant_isolation.py's
`# tenant-safe:` marker and check_permission_coverage.py's
`# permission-exempt:` marker.

auth.py is exempt by file: login/register/session/logout/password-reset
already have their own dedicated login-event trail (`_record_login_event`,
`entity_type="auth"`) — a parallel `_record_audit` call would just
duplicate it under a different entity type.

Usage: python3 scripts/check_audit_log_coverage.py
Exit 0 = every mutating endpoint writes an audit trail or has a reviewed exemption.
Exit 1 = at least one silently-unaudited mutating endpoint found (prints file:line).
"""
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTERS_DIR = REPO_ROOT / "backend" / "routers"
# Platform modules (docs/27) keep their own routers under backend/modules/<name>/routers/ —
# they get the same endpoint-safety gates as the core routers (added Oct 2, 2026 with EMR).
MODULE_ROUTERS_GLOB = (REPO_ROOT / "backend" / "modules").glob("*/routers/*.py")

# auth.py has its own parallel login-event audit trail (_record_login_event,
# entity_type="auth") — see module docstring.
EXEMPT_FILES = {"auth.py", "auth_helpers.py"}

MUTATING_METHODS = {"post", "put", "patch", "delete"}
AUDIT_CALL_NAMES = {"_record_audit", "_record_movement"}
EXEMPT_MARKER = "# audit-exempt:"


def _decorator_method(dec: ast.expr) -> str | None:
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "router":
        return None
    return func.attr if func.attr in MUTATING_METHODS else None


def _calls_audit_helper(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        callee = sub.func
        name = None
        if isinstance(callee, ast.Name):
            name = callee.id
        elif isinstance(callee, ast.Attribute):
            name = callee.attr
        if name in AUDIT_CALL_NAMES:
            return True
    return False


def check_file(path: Path) -> list[str]:
    violations = []
    source = path.read_text()
    lines = source.split("\n")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [f"{path.relative_to(REPO_ROOT)}: SyntaxError while parsing: {e}"]

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods = {m for dec in node.decorator_list if (m := _decorator_method(dec))}
        if not methods:
            continue

        start = node.lineno
        end = getattr(node, "end_lineno", None) or start
        body_text = "\n".join(lines[start - 1:end])

        if EXEMPT_MARKER in body_text:
            continue
        if _calls_audit_helper(node):
            continue

        methods_str = "/".join(sorted(m.upper() for m in methods))
        violations.append(f"{path.relative_to(REPO_ROOT)}:{start}: {methods_str} {node.name}() writes no audit trail")

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
        print("Audit log coverage check: OK — every mutating endpoint writes an "
              "audit trail (or has a reviewed # audit-exempt: comment).")
        return 0

    print("Audit log coverage check: FAILED")
    print()
    print("These mutating (POST/PUT/PATCH/DELETE) endpoints leave no record of")
    print("who did what — the exact gap found in sales_returns.py (zero")
    print("_record_audit calls for months) and customers.py (Sep 12, 2026)")
    print("(docs/15_ROADMAP.md RULE MISSES LOG). Add a call to the module's")
    print("_record_audit() helper. If this mutation is deliberately not worth")
    print("its own audit row, mark it with a `# audit-exempt: <reason>` comment")
    print("anywhere in the function body.")
    print()
    for v in all_violations:
        print(f"  {v}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
