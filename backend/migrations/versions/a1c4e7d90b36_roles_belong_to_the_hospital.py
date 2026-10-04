"""roles belong to the hospital (docs/32 P0)

Revision ID: a1c4e7d90b36
Revises: f6c3d0b8e425
Create Date: 2026-10-04

- Adds roles.chain_id. Every chain's roles are merged to one set owned by the hospital.
- Same name + same permissions as the home pharmacy's role → logins are repointed to it and the
  sibling row is kept but switched off (soft). Different permissions → kept as its own hospital
  role, renamed "<name> (<place>)", so nobody's access changes.
- Standalone pharmacies are untouched (chain_id stays NULL).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a1c4e7d90b36'
down_revision: Union[str, None] = 'f6c3d0b8e425'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('roles', sa.Column('chain_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_roles_chain', 'roles', 'chains', ['chain_id'], ['id'])
    conn = op.get_bind()

    chains = conn.execute(sa.text("SELECT id FROM chains")).scalars().all()
    for chain_id in chains:
        places = conn.execute(sa.text(
            "SELECT id, name FROM pharmacies WHERE chain_id = :c ORDER BY created_at, id"),
            {"c": chain_id}).all()
        if not places:
            continue
        home_id = places[0][0]
        conn.execute(sa.text("UPDATE roles SET chain_id = :c WHERE pharmacy_id = :p"),
                     {"c": chain_id, "p": home_id})
        for place_id, place_name in places[1:]:
            siblings = conn.execute(sa.text(
                "SELECT id, name, permissions, is_active FROM roles WHERE pharmacy_id = :p"),
                {"p": place_id}).all()
            for rid, rname, rperms, ractive in siblings:
                twin = conn.execute(sa.text(
                    "SELECT id, permissions FROM roles WHERE chain_id = :c AND name = :n AND is_active"),
                    {"c": chain_id, "n": rname}).first()
                if twin is not None and twin[1] == rperms:
                    for tbl in ("users", "user_store_roles"):
                        conn.execute(sa.text(f"UPDATE {tbl} SET role_id = :t WHERE role_id = :r"),
                                     {"t": twin[0], "r": rid})
                    conn.execute(sa.text(
                        "UPDATE roles SET is_active = false WHERE id = :r"), {"r": rid})
                    continue
                new_name = rname
                if twin is not None:
                    new_name = f"{rname} ({place_name})"[:100]
                conn.execute(sa.text(
                    "UPDATE roles SET chain_id = :c, name = :n WHERE id = :r"),
                    {"c": chain_id, "n": new_name, "r": rid})

    op.create_index('uq_roles_chain_name', 'roles', ['chain_id', 'name'], unique=True,
                    postgresql_where=sa.text('chain_id IS NOT NULL AND is_active'))


def downgrade() -> None:
    # Merged rows stay merged (logins keep working); only the ownership column goes.
    op.drop_index('uq_roles_chain_name', table_name='roles')
    op.drop_constraint('fk_roles_chain', 'roles', type_='foreignkey')
    op.drop_column('roles', 'chain_id')
