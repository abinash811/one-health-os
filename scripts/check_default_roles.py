#!/usr/bin/env python3
"""check_default_roles.py — fails if backend/constants.py's DEFAULT_ROLES grants a permission id that is not
defined in ALL_PERMISSIONS (a typo like 'patient_billing:colect' silently grants nothing and the role
just 403s), or if ALL_PERMISSIONS defines a duplicate id.

Why (Oct 3, 2026, B5 audit): the third time DEFAULT_ROLES gained permissions after clinics already existed
(suppliers Sep 12, EMR, patient billing) nothing checked the new ids at all, and stored roles drifted into
three generations (8/13/14 permissions). Storing role permissions per clinic means every new permission
also needs a data migration — see migrations/versions/*sync_clinic_role*.py for the pattern. This gate
catches the typo class; the migration habit is written in docs/15 → RULE MISSES LOG.

Usage: python3 scripts/check_default_roles.py   (exit 0 = clean)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from constants import ALL_PERMISSIONS, DEFAULT_ROLES  # noqa: E402


def main() -> int:
    defined = [p["id"] for g in ALL_PERMISSIONS.values() for p in g["permissions"]]
    problems = [f"duplicate permission id in ALL_PERMISSIONS: {i}" for i in sorted({d for d in defined if defined.count(d) > 1})]
    for role in DEFAULT_ROLES:
        for perm in role["permissions"]:
            if perm != "*" and perm not in defined:
                problems.append(f"role '{role['name']}' grants undefined permission '{perm}'")
    if problems:
        print("\n".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
