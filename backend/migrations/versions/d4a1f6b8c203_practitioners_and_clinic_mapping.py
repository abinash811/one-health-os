"""practitioners + practitioner_clinics (doctors as their own records)

Revision ID: d4a1f6b8c203
Revises: a7d3e91c4b20

docs/31_CORE_DOCTOR_SCOPE.md, phase 1. ADDITIVE ONLY — nothing existing is changed or dropped.
Backfill (idempotent): every user who is a doctor today (role `doctor`, or has an EMR doctor profile, schedule,
appointment or prescription) becomes a practitioner linked to that login, with their profile fields, plus one
clinic mapping for their own clinic carrying the consultation fee. Also gives existing clinics' stored `doctor`
and `receptionist` roles the new `doctors:view` permission (additive; the admin wildcard already covers edit).
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4a1f6b8c203'
down_revision: Union[str, None] = 'a7d3e91c4b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADDED = {"doctor": ["doctors:view"], "receptionist": ["doctors:view"]}

BACKFILL_PRACTITIONERS = """
INSERT INTO practitioners (id, chain_id, pharmacy_id, name, specialty, qualification, registration_no, phone,
                           user_id, is_external, is_active, created_at, updated_at)
SELECT gen_random_uuid(), ph.chain_id, u.pharmacy_id, u.name, p.specialty, p.qualification, p.registration_no,
       u.phone, u.id, false, u.is_active, now(), now()
FROM users u
JOIN roles r ON r.id = u.role_id
JOIN pharmacies ph ON ph.id = u.pharmacy_id
LEFT JOIN emr_doctor_profiles p ON p.user_id = u.id AND p.pharmacy_id = u.pharmacy_id
WHERE (r.name = 'doctor'
       OR p.id IS NOT NULL
       OR EXISTS (SELECT 1 FROM emr_doctor_schedules s WHERE s.doctor_user_id = u.id AND s.deleted_at IS NULL)
       OR EXISTS (SELECT 1 FROM emr_appointments a WHERE a.doctor_user_id = u.id)
       OR EXISTS (SELECT 1 FROM emr_prescriptions x WHERE x.doctor_user_id = u.id))
  AND NOT EXISTS (SELECT 1 FROM practitioners q WHERE q.user_id = u.id AND q.deleted_at IS NULL)
"""

BACKFILL_CLINICS = """
INSERT INTO practitioner_clinics (id, practitioner_id, pharmacy_id, consultation_fee_paise, is_active,
                                  created_at, updated_at)
SELECT gen_random_uuid(), q.id, q.pharmacy_id, p.consultation_fee_paise, true, now(), now()
FROM practitioners q
LEFT JOIN emr_doctor_profiles p ON p.user_id = q.user_id AND p.pharmacy_id = q.pharmacy_id
WHERE q.user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM practitioner_clinics c
                  WHERE c.practitioner_id = q.id AND c.pharmacy_id = q.pharmacy_id)
"""


def upgrade() -> None:
    op.create_table(
        'practitioners',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chain_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chains.id')),
        sa.Column('pharmacy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pharmacies.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('specialty', sa.String(100)),
        sa.Column('qualification', sa.String(200)),
        sa.Column('registration_no', sa.String(100)),
        sa.Column('phone', sa.String(10)),
        sa.Column('email', sa.String(200)),
        sa.Column('is_external', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('hospital', sa.String(200)),
        sa.Column('notes', sa.Text()),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_practitioners_pharmacy', 'practitioners', ['pharmacy_id'])
    op.create_index('idx_practitioners_chain', 'practitioners', ['chain_id'])
    op.create_index('idx_practitioners_name', 'practitioners', ['pharmacy_id', 'name'])
    op.create_index('uq_practitioners_user', 'practitioners', ['user_id'], unique=True,
                    postgresql_where=sa.text('user_id IS NOT NULL AND deleted_at IS NULL'))

    op.create_table(
        'practitioner_clinics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('practitioner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('practitioners.id'), nullable=False),
        sa.Column('pharmacy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pharmacies.id'), nullable=False),
        sa.Column('consultation_fee_paise', sa.Integer()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('practitioner_id', 'pharmacy_id', name='uq_practitioner_clinics'),
    )
    op.create_index('idx_practitioner_clinics_pharmacy', 'practitioner_clinics', ['pharmacy_id'])

    conn = op.get_bind()
    conn.execute(sa.text(BACKFILL_PRACTITIONERS))
    conn.execute(sa.text(BACKFILL_CLINICS))
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
    op.drop_index('idx_practitioner_clinics_pharmacy', table_name='practitioner_clinics')
    op.drop_table('practitioner_clinics')
    op.drop_index('uq_practitioners_user', table_name='practitioners')
    op.drop_index('idx_practitioners_name', table_name='practitioners')
    op.drop_index('idx_practitioners_chain', table_name='practitioners')
    op.drop_index('idx_practitioners_pharmacy', table_name='practitioners')
    op.drop_table('practitioners')
