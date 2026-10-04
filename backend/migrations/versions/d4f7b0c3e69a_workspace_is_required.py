"""workspace is required everywhere (docs/33 W4 — contract)

Revision ID: d4f7b0c3e69a
Revises: c3e6a9d2b58f

Re-checks the W1 backfill, then makes the workspace (`chain_id`) NOT NULL on pharmacies, roles, users,
clinics and practitioners. Role names are unique per workspace among active roles. A login's email is unique
per workspace — added only when no workspace already holds a duplicate (the code check always applies);
if some do, the index is skipped and a warning is logged so nothing existing is ever blocked or deleted.
"""
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4f7b0c3e69a'
down_revision: Union[str, None] = 'c3e6a9d2b58f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()
    for pharmacy_id, name, owner_id in conn.execute(sa.text(
            "SELECT p.id, p.name, (SELECT u.id FROM users u WHERE u.pharmacy_id = p.id AND u.is_admin "
            "ORDER BY u.created_at LIMIT 1) FROM pharmacies p WHERE p.chain_id IS NULL")).all():
        chain_id = conn.execute(sa.text(
            "INSERT INTO chains (id, name, owner_user_id, is_active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :n, :o, true, now(), now()) RETURNING id"),
            {"n": name, "o": owner_id}).scalar_one()
        conn.execute(sa.text("UPDATE pharmacies SET chain_id = :c WHERE id = :p"), {"c": chain_id, "p": pharmacy_id})
    conn.execute(sa.text("UPDATE roles r SET chain_id = p.chain_id FROM pharmacies p "
                         "WHERE r.pharmacy_id = p.id AND r.chain_id IS NULL"))
    conn.execute(sa.text("UPDATE users u SET chain_id = p.chain_id FROM pharmacies p "
                         "WHERE u.pharmacy_id = p.id AND u.chain_id IS NULL"))
    conn.execute(sa.text("UPDATE practitioners x SET chain_id = p.chain_id FROM pharmacies p "
                         "WHERE x.pharmacy_id = p.id AND x.chain_id IS NULL"))
    conn.execute(sa.text("UPDATE clinics c SET chain_id = p.chain_id FROM pharmacies p "
                         "WHERE c.linked_pharmacy_id = p.id AND c.chain_id IS NULL"))

    for table in ("pharmacies", "roles", "users", "clinics", "practitioners"):
        op.alter_column(table, "chain_id", nullable=False)

    op.drop_index('uq_roles_chain_name', table_name='roles')
    op.create_index('uq_roles_chain_name', 'roles', ['chain_id', 'name'], unique=True,
                    postgresql_where=sa.text('is_active'))

    dupes = conn.execute(sa.text(
        "SELECT count(*) FROM (SELECT 1 FROM users GROUP BY chain_id, email HAVING count(*) > 1) d")).scalar_one()
    if dupes:
        log.warning("W4: %s workspace(s) hold the same email twice — unique (workspace, email) index skipped; "
                    "the application check still applies.", dupes)
    else:
        op.create_index('uq_users_workspace_email', 'users', ['chain_id', 'email'], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS uq_users_workspace_email"))
    op.drop_index('uq_roles_chain_name', table_name='roles')
    op.create_index('uq_roles_chain_name', 'roles', ['chain_id', 'name'], unique=True,
                    postgresql_where=sa.text('chain_id IS NOT NULL AND is_active'))
    for table in ("pharmacies", "roles", "users", "clinics", "practitioners"):
        op.alter_column(table, "chain_id", nullable=True)
