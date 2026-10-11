"""Drop legacy columns: EMR doctor_user_id, emr_doctor_profiles, per-place role_id (Oct 11, 2026)

Revision ID: a8e2c5f1d047
Revises: f7c0e3a6b92d

CONTRACT step of two finished expand/backfill/switch moves — nothing reads or writes any of this any more:
- `emr_doctor_schedules / emr_appointments / emr_prescriptions.doctor_user_id` — doctors are their own records
  (`practitioner_id`, docs/31); verified before dropping that every row's practitioner points at the same person.
- `emr_doctor_profiles` — its specialty / qualification / registration / fee live on `practitioners` and
  `practitioner_clinics`; verified before dropping that nothing differed.
- `user_store_roles.role_id` and `user_clinic_access.role_id` — a person has ONE role (`users.role_id`) at every
  place (Abinash's decision, Oct 11, 2026); these two tables now only say where someone may work.

DOWNGRADE puts the columns back and refills them from what remains: `role_id` from the person's own role,
`doctor_user_id` from the doctor record's login. The profiles table comes back empty (nothing reads it).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a8e2c5f1d047'
down_revision: Union[str, None] = 'f7c0e3a6b92d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCTOR_TABLES = ["emr_doctor_schedules", "emr_appointments", "emr_prescriptions"]
ACCESS_TABLES = ["user_store_roles", "user_clinic_access"]


def upgrade() -> None:
    for table in DOCTOR_TABLES:
        op.drop_column(table, "doctor_user_id")
    op.drop_table("emr_doctor_profiles")
    for table in ACCESS_TABLES:
        op.drop_column(table, "role_id")


def downgrade() -> None:
    for table in ACCESS_TABLES:
        op.add_column(table, sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} t SET role_id = u.role_id FROM users u WHERE u.id = t.user_id")
        op.alter_column(table, "role_id", nullable=False)
        op.create_foreign_key(f"{table}_role_id_fkey", table, "roles", ["role_id"], ["id"])

    op.create_table(
        "emr_doctor_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pharmacy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pharmacies.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("specialty", sa.String(100)),
        sa.Column("qualification", sa.String(200)),
        sa.Column("registration_no", sa.String(100)),
        sa.Column("consultation_fee_paise", sa.Integer()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pharmacy_id", "user_id", name="uq_emr_doctor_profiles_user"),
    )

    for table in DOCTOR_TABLES:
        op.add_column(table, sa.Column("doctor_user_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"{table}_doctor_user_id_fkey", table, "users", ["doctor_user_id"], ["id"])
        op.execute(f"UPDATE {table} t SET doctor_user_id = p.user_id FROM practitioners p "
                   f"WHERE p.id = t.practitioner_id AND p.user_id IS NOT NULL")
