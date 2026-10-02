#!/usr/bin/env python3
"""check_db_session_scope.py — fails if any backend endpoint/dependency uses a bare
`Depends(get_db)` instead of the shared `DbSession` from backend/deps.py.

Why this exists (found Oct 2, 2026): with FastAPI 0.118+, a yield-dependency's exit code
runs AFTER the response is sent unless it is declared `scope="function"`. `get_db` commits
in its exit code, so every `Depends(get_db)` endpoint answered "200 OK" BEFORE its data was
committed. Proven with a standalone app (response in 0.02s, commit 1s later). Consequences:
the next request could not see the data it had just created (random "Product not found" /
"Invalid credentials" failures under load, 1–3 per full test run for weeks, wrongly written
off as flaky), and a failed commit would never have reached the client — unacceptable for
money. `DbSession` (deps.py) is `Depends(get_db, scope="function")`; this gate keeps anyone
from reintroducing the bare form.

Usage: python3 scripts/check_db_session_scope.py   (exit 0 = clean, 1 = offenders printed)
"""
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
BARE = re.compile(r"Depends\(\s*get_db\s*[,)]")
ALLOWED = {BACKEND / "deps.py"}


def main() -> int:
    bad = []
    for path in BACKEND.rglob("*.py"):
        parts = path.relative_to(BACKEND).parts
        if parts[0] in ("venv", "tests", "migrations") or path in ALLOWED:
            continue
        text = path.read_text()
        for m in BARE.finditer(text):
            bad.append(f"{path.relative_to(BACKEND.parent)}:{text.count(chr(10), 0, m.start()) + 1}")
    if bad:
        print("Bare Depends(get_db) found — use `db: AsyncSession = DbSession` (from deps import DbSession):")
        print("\n".join(f"  {b}" for b in bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
