#!/usr/bin/env python3
"""check_workspace_identity.py — fails if backend code scopes LOGINS or ROLES by a single pharmacy.

Why (docs/33_WORKSPACE_SCOPE.md W4, Oct 4, 2026): logins, roles and Team belong to the WORKSPACE (hospital), not to
one pharmacy. A query like `UserORM.pharmacy_id == x` or `RoleORM.pharmacy_id == x` quietly brings back the old
"one pharmacy = one tenant" behaviour — Team would show only some of the hospital's people. Use
services/workspace.py (caller_workspace, get_workspace_user_or_404, list_workspace_users) and
services/role_scope.py (find_role, list_roles, get_role_or_404) instead.

Flags `UserORM.pharmacy_id` / `RoleORM.pharmacy_id` in backend routers, modules and services. A reviewed exception
carries a trailing `# workspace-safe: <reason>` comment. Exit 0 = clean, 1 = prints file:line."""
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
DIRS = ("routers", "modules", "services")
PATTERN = re.compile(r"\b(UserORM|RoleORM)\.pharmacy_id\b")


def main() -> int:
    bad = []
    for d in DIRS:
        for path in (BACKEND / d).rglob("*.py"):
            for i, line in enumerate(path.read_text().split("\n"), start=1):
                if PATTERN.search(line) and "# workspace-safe:" not in line:
                    bad.append(f"{path.relative_to(BACKEND.parent)}:{i}: {line.strip()}")
    for line in bad:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
