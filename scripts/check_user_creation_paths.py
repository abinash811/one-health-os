#!/usr/bin/env python3
"""check_user_creation_paths.py — fails if backend code creates a `User` row without also writing the matching
store-access row (`sync_user_store_role`, docs/26_MULTI_CHAIN_SCOPE.md).

Why: found Oct 3, 2026 — `seed_admin.py` created admins with no `user_store_roles` row, so the sidebar store
switcher read "Loading…" and the Doctors "Works at" list came up empty for exactly the person who sets the app up.
The docs said every creation path wrote the row; nothing checked.

Flags: any backend .py file (outside tests, migrations, venv) that builds a `User(...)` / `UserORM(...)` with a
`password_hash=` and never mentions `sync_user_store_role`. Exit 0 = clean, 1 = prints file:line."""
import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
SKIP_PARTS = {"tests", "migrations", "venv", "__pycache__"}


def main() -> int:
    bad = []
    for path in BACKEND.rglob("*.py"):
        if SKIP_PARTS & set(path.relative_to(BACKEND).parts):
            continue
        src = path.read_text()
        if "password_hash" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("User", "UserORM")
                    and any(k.arg == "password_hash" for k in node.keywords)
                    and "sync_user_store_role" not in src):
                bad.append(f"{path.relative_to(BACKEND.parent)}:{node.lineno}: creates a User but never calls sync_user_store_role")
    for line in bad:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
