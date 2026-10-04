"""user_clinic_access + users.clinic_id (docs/32 P2a)

Revision ID: e6b9d2f5a81c
Revises: d4f7b0c3e69a

ADDITIVE. Which clinics a login may open (with their role there) and the clinic they are working at now.
Backfill: every store-access row at a place that is also a clinic (same id) becomes a clinic-access row with
the same role; each login's active clinic = its home place when that is a clinic.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e6b9d2f5a81c'
down_revision: Union[str, None] = 'd4f7b0c3e69a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_clinic_access',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('clinic_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clinics.id'), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('roles.id'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'clinic_id', name='uq_user_clinic_access'),
    )
    op.add_column('users', sa.Column('clinic_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_users_clinic', 'users', 'clinics', ['clinic_id'], ['id'])

    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO user_clinic_access (id, user_id, clinic_id, role_id) "
        "SELECT gen_random_uuid(), usr.user_id, usr.pharmacy_id, usr.role_id "
        "FROM user_store_roles usr JOIN clinics c ON c.id = usr.pharmacy_id "
        "ON CONFLICT (user_id, clinic_id) DO NOTHING"))
    conn.execute(sa.text(
        "UPDATE users u SET clinic_id = u.pharmacy_id "
        "WHERE EXISTS (SELECT 1 FROM user_clinic_access a WHERE a.user_id = u.id AND a.clinic_id = u.pharmacy_id)"))


def downgrade() -> None:
    op.drop_constraint('fk_users_clinic', 'users', type_='foreignkey')
    op.drop_column('users', 'clinic_id')
    op.drop_table('user_clinic_access')
