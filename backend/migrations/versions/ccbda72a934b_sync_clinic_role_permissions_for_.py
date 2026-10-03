"""sync clinic role permissions for prescriptions and patient billing

Revision ID: ccbda72a934b
Revises: 1462660fbf8c

Data-only migration (same idea as 25ea9247b0c3). constants.py's DEFAULT_ROLES gained permissions for the
`doctor` and `receptionist` system roles after clinics may already have been created (prescriptions:*,
patient_billing:*). Editing the Python constant never touches roles already stored in a clinic's database,
so those clinics' doctors could not write prescriptions and their front desk could not collect fees.

ADDITIVE only: each permission below is added if missing; nothing an admin granted is removed. Scoped to
is_system_role = true rows. Found in the B5 audit (Oct 3, 2026): dev DB had `doctor` roles holding 8, 13 and 14
permissions — three different generations.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'ccbda72a934b'
down_revision: Union[str, None] = '1462660fbf8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADDED = {
    "doctor": [
        "prescriptions:view", "prescriptions:create", "prescriptions:edit", "prescriptions:issue",
        "prescriptions:cancel", "patient_billing:view",
    ],
    "receptionist": [
        "prescriptions:view", "patient_billing:view", "patient_billing:charge", "patient_billing:invoice",
        "patient_billing:collect",
    ],
}


def upgrade() -> None:
    conn = op.get_bind()
    for role, perms in ADDED.items():
        conn.execute(
            sa.text(
                "UPDATE roles SET permissions = ("
                "  SELECT jsonb_agg(DISTINCT e) FROM jsonb_array_elements(permissions || CAST(:add AS jsonb)) e"
                ") WHERE name = :role AND is_system_role = true AND jsonb_typeof(permissions) = 'array'"),
            {"add": json.dumps(perms), "role": role})


def downgrade() -> None:
    conn = op.get_bind()
    for role, perms in ADDED.items():
        conn.execute(
            sa.text(
                "UPDATE roles SET permissions = COALESCE(("
                "  SELECT jsonb_agg(e) FROM jsonb_array_elements(permissions) e"
                "  WHERE e NOT IN (SELECT jsonb_array_elements(CAST(:add AS jsonb)))"
                "), '[]'::jsonb) WHERE name = :role AND is_system_role = true AND jsonb_typeof(permissions) = 'array'"),
            {"add": json.dumps(perms), "role": role})
