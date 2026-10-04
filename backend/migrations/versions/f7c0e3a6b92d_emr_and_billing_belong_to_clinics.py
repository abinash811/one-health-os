"""EMR + patient billing tables belong to clinics, not pharmacies (docs/32 P2b)

Revision ID: f7c0e3a6b92d
Revises: e6b9d2f5a81c

Each listed table's `pharmacy_id` becomes `clinic_id` and points at `clinics`. This works without copying any
data because every place that already holds EMR / patient-billing data has a clinic with the SAME id (P1
backfill; the loop below also creates any missing one first, with access rows for the people who worked
there). Indexes named `*pharmacy*` are renamed to `*clinic*`.

DOWNGRADE note: it puts the column back and re-points it at pharmacies — only possible while every clinic still
shares its id with a pharmacy (i.e. before new clinics have data).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f7c0e3a6b92d'
down_revision: Union[str, None] = 'e6b9d2f5a81c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["emr_patients", "emr_doctor_schedules", "emr_appointments", "emr_prescriptions",
          "emr_prescription_items", "emr_settings", "practitioner_clinics",
          "pb_invoices", "pb_charge_items", "pb_payments"]


def _fk_names(conn, table: str, column: str, ref: str) -> list[str]:
    return list(conn.execute(sa.text(
        "SELECT c.conname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
        "WHERE c.contype = 'f' AND c.conrelid = CAST(:t AS regclass) AND a.attname = :col "
        "AND c.confrelid = CAST(:r AS regclass)"), {"t": table, "col": column, "r": ref}).scalars())


def _rename_indexes(conn, table: str, old: str, new: str) -> None:
    for (name,) in conn.execute(sa.text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = :t "
            "AND indexname LIKE :p"), {"t": table, "p": f"%{old}%"}).all():
        conn.execute(sa.text(f'ALTER INDEX "{name}" RENAME TO "{name.replace(old, new)}"'))


def upgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(sa.text(
            "INSERT INTO clinics (id, chain_id, linked_pharmacy_id, name, address, city, state, pincode, phone, "
            "email, is_active, created_at, updated_at) "
            f"SELECT p.id, p.chain_id, p.id, p.name, p.address, p.city, p.state, p.pincode, p.phone, p.email, "
            f"p.is_active, now(), now() FROM pharmacies p WHERE p.id IN (SELECT DISTINCT pharmacy_id FROM {table}) "
            "AND NOT EXISTS (SELECT 1 FROM clinics c WHERE c.id = p.id)"))
    conn.execute(sa.text(
        "INSERT INTO user_clinic_access (id, user_id, clinic_id, role_id) "
        "SELECT gen_random_uuid(), usr.user_id, usr.pharmacy_id, usr.role_id "
        "FROM user_store_roles usr JOIN clinics c ON c.id = usr.pharmacy_id "
        "ON CONFLICT (user_id, clinic_id) DO NOTHING"))
    conn.execute(sa.text(
        "UPDATE users u SET clinic_id = u.pharmacy_id WHERE u.clinic_id IS NULL AND EXISTS "
        "(SELECT 1 FROM user_clinic_access a WHERE a.user_id = u.id AND a.clinic_id = u.pharmacy_id)"))

    for table in TABLES:
        for fk in _fk_names(conn, table, "pharmacy_id", "pharmacies"):
            op.drop_constraint(fk, table, type_="foreignkey")
        op.alter_column(table, "pharmacy_id", new_column_name="clinic_id")
        op.create_foreign_key(f"fk_{table}_clinic", table, "clinics", ["clinic_id"], ["id"])
        _rename_indexes(conn, table, "pharmacy", "clinic")


def downgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        _rename_indexes(conn, table, "clinic", "pharmacy")
        op.drop_constraint(f"fk_{table}_clinic", table, type_="foreignkey")
        op.alter_column(table, "clinic_id", new_column_name="pharmacy_id")
        op.create_foreign_key(f"fk_{table}_pharmacy", table, "pharmacies", ["pharmacy_id"], ["id"])
