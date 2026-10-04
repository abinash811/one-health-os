"""clinics table + clinics/pharmacies permissions (docs/32 P1)

Revision ID: b2d5f8a1c47e
Revises: a1c4e7d90b36

ADDITIVE ONLY. Creates `clinics`. Every pharmacy record that already holds EMR data gets a clinic row with
the SAME id (so P2 can move the EMR tables over without copying anything), named and addressed from its EMR
clinic profile when set. Also gives existing hospitals' stored `doctor` / `receptionist` roles `clinics:view`.
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b2d5f8a1c47e'
down_revision: Union[str, None] = 'a1c4e7d90b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADDED = {"doctor": ["clinics:view"], "receptionist": ["clinics:view"]}

BACKFILL = """
INSERT INTO clinics (id, chain_id, linked_pharmacy_id, name, address, city, state, pincode, phone, email,
                     registration_no, is_active, created_at, updated_at)
SELECT p.id, p.chain_id, p.id, COALESCE(NULLIF(es.clinic_name, ''), p.name),
       COALESCE(NULLIF(es.clinic_address, ''), p.address), p.city, p.state, p.pincode,
       COALESCE(NULLIF(es.clinic_phone, ''), p.phone), COALESCE(NULLIF(es.clinic_email, ''), p.email),
       es.registration_no, p.is_active, now(), now()
FROM pharmacies p
LEFT JOIN emr_settings es ON es.pharmacy_id = p.id
WHERE (EXISTS (SELECT 1 FROM emr_settings x WHERE x.pharmacy_id = p.id)
    OR EXISTS (SELECT 1 FROM emr_patients x WHERE x.pharmacy_id = p.id)
    OR EXISTS (SELECT 1 FROM emr_appointments x WHERE x.pharmacy_id = p.id)
    OR EXISTS (SELECT 1 FROM emr_doctor_schedules x WHERE x.pharmacy_id = p.id)
    OR EXISTS (SELECT 1 FROM practitioner_clinics x WHERE x.pharmacy_id = p.id))
  AND NOT EXISTS (SELECT 1 FROM clinics c WHERE c.id = p.id)
"""


def upgrade() -> None:
    op.create_table(
        'clinics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chain_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chains.id'), nullable=True),
        sa.Column('linked_pharmacy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pharmacies.id'),
                  nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('address', sa.String(500)),
        sa.Column('city', sa.String(100)),
        sa.Column('state', sa.String(100)),
        sa.Column('pincode', sa.String(6)),
        sa.Column('phone', sa.String(20)),
        sa.Column('email', sa.String(200)),
        sa.Column('registration_no', sa.String(100)),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_clinics_chain', 'clinics', ['chain_id'])
    op.create_index('idx_clinics_linked_pharmacy', 'clinics', ['linked_pharmacy_id'])

    conn = op.get_bind()
    conn.execute(sa.text(BACKFILL))
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
    op.drop_index('idx_clinics_linked_pharmacy', table_name='clinics')
    op.drop_index('idx_clinics_chain', table_name='clinics')
    op.drop_table('clinics')
