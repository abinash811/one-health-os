"""every pharmacy lives in a workspace; logins carry their workspace (docs/33 W1)

Revision ID: c3e6a9d2b58f
Revises: b2d5f8a1c47e

ADDITIVE. Adds users.chain_id (nullable until the contract step). Backfill (idempotent): every pharmacy that
is still standing alone gets a workspace of its own (named after the pharmacy; owned by its earliest admin
login); its roles, clinics and doctors move under it; every login gets its pharmacy's workspace. Nobody's
permissions change — same rows, new owner.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c3e6a9d2b58f'
down_revision: Union[str, None] = 'b2d5f8a1c47e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('chain_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_users_chain', 'users', 'chains', ['chain_id'], ['id'])
    op.create_index('idx_users_chain', 'users', ['chain_id'])

    conn = op.get_bind()
    loners = conn.execute(sa.text(
        "SELECT p.id, p.name, "
        "  (SELECT u.id FROM users u WHERE u.pharmacy_id = p.id AND u.is_admin ORDER BY u.created_at LIMIT 1) "
        "FROM pharmacies p WHERE p.chain_id IS NULL")).all()
    for pharmacy_id, name, owner_id in loners:
        chain_id = conn.execute(sa.text(
            "INSERT INTO chains (id, name, owner_user_id, is_active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :n, :o, true, now(), now()) RETURNING id"),
            {"n": name, "o": owner_id}).scalar_one()
        conn.execute(sa.text("UPDATE pharmacies SET chain_id = :c WHERE id = :p"), {"c": chain_id, "p": pharmacy_id})
        conn.execute(sa.text("UPDATE roles SET chain_id = :c WHERE pharmacy_id = :p AND chain_id IS NULL"),
                     {"c": chain_id, "p": pharmacy_id})
        conn.execute(sa.text("UPDATE clinics SET chain_id = :c WHERE linked_pharmacy_id = :p AND chain_id IS NULL"),
                     {"c": chain_id, "p": pharmacy_id})
    conn.execute(sa.text("UPDATE practitioners pr SET chain_id = p.chain_id FROM pharmacies p "
                         "WHERE pr.pharmacy_id = p.id AND pr.chain_id IS NULL"))
    conn.execute(sa.text("UPDATE users u SET chain_id = p.chain_id FROM pharmacies p "
                         "WHERE u.pharmacy_id = p.id AND u.chain_id IS NULL"))


def downgrade() -> None:
    # The workspaces formed for standalone pharmacies stay (harmless: a workspace of one behaves like none).
    op.drop_index('idx_users_chain', table_name='users')
    op.drop_constraint('fk_users_chain', 'users', type_='foreignkey')
    op.drop_column('users', 'chain_id')
