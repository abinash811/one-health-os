"""backfill missing user_store_roles rows

Revision ID: e5b2c9a7d314
Revises: d4a1f6b8c203

Every user must have a store-access row for their home store (docs/26_MULTI_CHAIN_SCOPE.md). Logins created by
`seed_admin.py` (and any other path that skipped the helper) have none, so the sidebar store switcher and the
Doctors "Works at" list came up empty for them. ADDITIVE and idempotent: inserts only the missing row, mirroring
`users.pharmacy_id` / `users.role_id`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5b2c9a7d314'
down_revision: Union[str, None] = 'd4a1f6b8c203'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        INSERT INTO user_store_roles (id, user_id, pharmacy_id, role_id, created_at, updated_at)
        SELECT gen_random_uuid(), u.id, u.pharmacy_id, u.role_id, now(), now()
        FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM user_store_roles s
                          WHERE s.user_id = u.id AND s.pharmacy_id = u.pharmacy_id)
    """))


def downgrade() -> None:
    pass  # the rows are correct data; removing them again would only re-create the bug
