"""add appointments:consult to the default doctor roles (Oct 11, 2026)

Revision ID: b9f3d6a2e158
Revises: a8e2c5f1d047

Data-only, ADDITIVE migration (same idea as ccbda72a934b). Starting / completing a consultation used to share the
`appointments:edit` tick with rescheduling, so a receptionist could run a consultation. It now has its own tick,
`appointments:consult`; this gives it to the stored `doctor` system roles so doctors keep working. Nothing is
removed from any role. A custom role that should start consultations must be given the new tick in
Roles & Permissions (administrators always have every tick).
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b9f3d6a2e158'
down_revision: Union[str, None] = 'a8e2c5f1d047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADD = json.dumps(["appointments:consult"])


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE roles SET permissions = ("
        "  SELECT jsonb_agg(DISTINCT e) FROM jsonb_array_elements(permissions || CAST(:add AS jsonb)) e"
        ") WHERE name = 'doctor' AND is_system_role = true AND jsonb_typeof(permissions) = 'array'"), {"add": ADD})


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE roles SET permissions = COALESCE(("
        "  SELECT jsonb_agg(e) FROM jsonb_array_elements(permissions) e WHERE e <> to_jsonb(CAST(:p AS text))"
        "), '[]'::jsonb) WHERE name = 'doctor' AND is_system_role = true AND jsonb_typeof(permissions) = 'array'"),
        {"p": "appointments:consult"})
