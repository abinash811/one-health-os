"""EMR schedules / appointments / prescriptions point at practitioners (doctor records), not logins

Revision ID: f6c3d0b8e425
Revises: e5b2c9a7d314

docs/31_CORE_DOCTOR_SCOPE.md, phase 2. Adds `practitioner_id` to emr_doctor_schedules, emr_appointments and
emr_prescriptions, fills it from the old `doctor_user_id` through the practitioner linked to that login (first
re-running the phase-1 backfill, idempotently, so any doctor login that appeared since still gets a profile),
then makes it NOT NULL and moves the token / slot uniqueness onto it. `doctor_user_id` stays (now nullable, no
longer written) so history is readable until phase 4 drops it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f6c3d0b8e425'
down_revision: Union[str, None] = 'e5b2c9a7d314'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("emr_doctor_schedules", "emr_appointments", "emr_prescriptions")

BACKFILL_PRACTITIONERS = """
INSERT INTO practitioners (id, chain_id, pharmacy_id, name, specialty, qualification, registration_no, phone,
                           user_id, is_external, is_active, created_at, updated_at)
SELECT gen_random_uuid(), ph.chain_id, u.pharmacy_id, u.name, p.specialty, p.qualification, p.registration_no,
       u.phone, u.id, false, u.is_active, now(), now()
FROM users u
JOIN pharmacies ph ON ph.id = u.pharmacy_id
LEFT JOIN emr_doctor_profiles p ON p.user_id = u.id AND p.pharmacy_id = u.pharmacy_id
WHERE (EXISTS (SELECT 1 FROM emr_doctor_schedules s WHERE s.doctor_user_id = u.id)
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
WHERE q.user_id IS NOT NULL AND q.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM practitioner_clinics c WHERE c.practitioner_id = q.id AND c.pharmacy_id = q.pharmacy_id)
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(BACKFILL_PRACTITIONERS))
    conn.execute(sa.text(BACKFILL_CLINICS))

    for table in TABLES:
        op.add_column(table, sa.Column('practitioner_id', postgresql.UUID(as_uuid=True),
                                       sa.ForeignKey('practitioners.id'), nullable=True))
        conn.execute(sa.text(
            f"UPDATE {table} t SET practitioner_id = p.id FROM practitioners p "
            "WHERE p.user_id = t.doctor_user_id AND p.deleted_at IS NULL"))
        # Fails loudly (rather than silently losing a doctor) if any row could not be mapped.
        op.alter_column(table, 'practitioner_id', nullable=False)
        op.alter_column(table, 'doctor_user_id', nullable=True)

    op.drop_index('idx_emr_doctor_schedules_doctor', table_name='emr_doctor_schedules')
    op.create_index('idx_emr_doctor_schedules_practitioner', 'emr_doctor_schedules',
                    ['pharmacy_id', 'practitioner_id', 'weekday'])

    op.drop_constraint('uq_emr_appointments_token', 'emr_appointments', type_='unique')
    op.create_unique_constraint('uq_emr_appointments_token', 'emr_appointments',
                                ['pharmacy_id', 'practitioner_id', 'appointment_date', 'token_number'])
    op.drop_index('uq_emr_appointments_slot', table_name='emr_appointments')
    op.create_index('uq_emr_appointments_slot', 'emr_appointments',
                    ['pharmacy_id', 'practitioner_id', 'appointment_date', 'start_time'], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL AND start_time IS NOT NULL "
                                             "AND status NOT IN ('cancelled', 'no_show')"))


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_index('uq_emr_appointments_slot', table_name='emr_appointments')
    op.create_index('uq_emr_appointments_slot', 'emr_appointments',
                    ['pharmacy_id', 'doctor_user_id', 'appointment_date', 'start_time'], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL AND start_time IS NOT NULL "
                                             "AND status NOT IN ('cancelled', 'no_show')"))
    op.drop_constraint('uq_emr_appointments_token', 'emr_appointments', type_='unique')
    op.create_unique_constraint('uq_emr_appointments_token', 'emr_appointments',
                                ['pharmacy_id', 'doctor_user_id', 'appointment_date', 'token_number'])
    op.drop_index('idx_emr_doctor_schedules_practitioner', table_name='emr_doctor_schedules')
    op.create_index('idx_emr_doctor_schedules_doctor', 'emr_doctor_schedules',
                    ['pharmacy_id', 'doctor_user_id', 'weekday'])
    for table in TABLES:
        # rows written after the upgrade for a doctor with no login have no doctor_user_id; the column stays nullable
        conn.execute(sa.text(
            f"UPDATE {table} t SET doctor_user_id = p.user_id FROM practitioners p "
            "WHERE p.id = t.practitioner_id AND t.doctor_user_id IS NULL"))
        op.drop_column(table, 'practitioner_id')
