"""add users.is_admin (admin is a checkbox, not a role)

Revision ID: a7d3e91c4b20
Revises: ccbda72a934b

Admin becomes a flag on the user, separate from the clinical role, so one person can be a Doctor AND an admin.
Backfill: everyone currently in the `admin` role gets is_admin = true, so nobody loses access. The `admin` role row
itself is kept (existing users still point at it); it is just no longer offered when adding a member.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7d3e91c4b20'
down_revision: Union[str, None] = 'ccbda72a934b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))
    op.execute(
        "UPDATE users SET is_admin = true WHERE role_id IN (SELECT id FROM roles WHERE name = 'admin')")


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
