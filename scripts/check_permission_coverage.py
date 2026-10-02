#!/usr/bin/env python3
"""check_permission_coverage.py — fails if a mutating backend endpoint
(POST/PUT/PATCH/DELETE) has no role/permission check anywhere in its body.

Why this exists: found Sep 12-16, 2026 (docs/15_ROADMAP.md RULE MISSES LOG)
that the real permissions system (roles table, has_permission(),
ALL_PERMISSIONS catalog) was wired into Purchases/Purchase Returns only —
Billing, Inventory, Customers, Reports, and Settings were fully open to any
authenticated user regardless of role, for months, because each module's
own review checked that module's business logic, never "does this module's
writes need a permission gate like Purchases got." Even inside modules that
DID get gated, the gate reached some endpoints and not others at least
three separate times (Suppliers' toggle-status, Customers' doctor
endpoints found in a later pass, Suppliers create/update/delete done but
toggle-status missed) — the exact "reached some call sites, not all" shape
Manifesto rule 11 names. This script closes the gap the same way
check_tenant_isolation.py closed the cross-tenant one: catch every
recurrence at once, going forward, instead of relying on someone
remembering to re-check.

Flags: any POST/PUT/PATCH/DELETE endpoint function in backend/routers/*.py
whose body contains no call to a permission-check helper (any
`_require_*_permission(`, `has_permission(`, `require_admin_or_super(`, or
`resolve_store_override_for_write(` — added Sep 27, 2026 when the HQ-buyer
store picker, docs/26_MULTI_CHAIN_SCOPE.md Section 3 #3, introduced a
permission check that itself lives inside a shared helper rather than a
direct call in the endpoint body) and no `# permission-exempt: <reason>`
comment anywhere in its body.

A `# permission-exempt: <reason>` comment marks a deliberate, reviewed
exception (e.g. a self-service "change my own password" endpoint, or a
pre-authentication endpoint) — same precedent as check_tenant_isolation.py's
`# tenant-safe:` marker.

auth.py is exempt by file, not by per-line comment: every mutating endpoint
in it (register, login, forgot-password, reset-password, session, logout)
is a pre-authentication or self-only identity primitive that a role/
permission concept does not apply to at all — the same class of exemption
check_tenant_isolation.py already gives auth_helpers.py.

Usage: python3 scripts/check_permission_coverage.py
Exit 0 = every mutating endpoint has a permission check or a reviewed exemption.
Exit 1 = at least one unguarded mutating endpoint found (prints file:line).
"""
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTERS_DIR = REPO_ROOT / "backend" / "routers"
# Platform modules (docs/27) keep their own routers under backend/modules/<name>/routers/ —
# they get the same endpoint-safety gates as the core routers (added Oct 2, 2026 with EMR).
MODULE_ROUTERS_GLOB = (REPO_ROOT / "backend" / "modules").glob("*/routers/*.py")

# Pre-authentication / self-only identity primitives — a role/permission
# concept does not apply to any endpoint in this file. See module docstring.
EXEMPT_FILES = {"auth.py", "auth_helpers.py"}

MUTATING_METHODS = {"post", "put", "patch", "delete"}
PERMISSION_CALL_NAMES = {"has_permission", "require_admin_or_super", "resolve_store_override_for_write"}
PERMISSION_CALL_PREFIX = "_require_"
EXEMPT_MARKER = "# permission-exempt:"


def _decorator_method(dec: ast.expr) -> str | None:
    """Return 'post'/'put'/'patch'/'delete' if this decorator is
    @router.<method>(...), else None."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "router":
        return None
    return func.attr if func.attr in MUTATING_METHODS else None


def _calls_permission_helper(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        callee = sub.func
        name = None
        if isinstance(callee, ast.Name):
            name = callee.id
        elif isinstance(callee, ast.Attribute):
            name = callee.attr
        is_require_helper = name and name.startswith(PERMISSION_CALL_PREFIX) and name.endswith("_permission")
        if name in PERMISSION_CALL_NAMES or is_require_helper:
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
        if _calls_permission_helper(node):
            continue

        methods_str = "/".join(sorted(m.upper() for m in methods))
        violations.append(f"{path.relative_to(REPO_ROOT)}:{start}: {methods_str} {node.name}() has no permission check")

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
        print("Permission coverage check: OK — every mutating endpoint has a "
              "permission check (or a reviewed # permission-exempt: comment).")
        return 0

    print("Permission coverage check: FAILED")
    print()
    print("These mutating (POST/PUT/PATCH/DELETE) endpoints have no role/")
    print("permission check anywhere in their body — the exact gap found")
    print("Sep 2026 across Billing/Inventory/Customers/Reports/Settings")
    print("(docs/15_ROADMAP.md RULE MISSES LOG). Add a call to the module's")
    print("_require_<module>_permission() helper (or has_permission()/")
    print("require_admin_or_super() for an admin-only action). If this")
    print("endpoint is deliberately open to any authenticated user (e.g. a")
    print("self-service action), mark it with a `# permission-exempt: <reason>`")
    print("comment anywhere in the function body.")
    print()
    for v in all_violations:
        print(f"  {v}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
