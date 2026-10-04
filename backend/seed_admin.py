#!/usr/bin/env python3
"""
seed_admin.py — Bootstrap a PharmaCare PostgreSQL database.

Creates (idempotently):
  1. A Pharmacy record
  2. The four system roles  (admin / manager / cashier / inventory_staff)
  3. PharmacySettings with sensible defaults
  4. An admin user

Run from the backend/ directory:

    python seed_admin.py                        # uses defaults below
    python seed_admin.py --email me@rx.com --password Secret123 --name "Dr. Admin"

Safe to run multiple times — skips anything that already exists.
"""
from __future__ import annotations
from models.users import Role, User
from models.pharmacy import Pharmacy, PharmacySettings
from database import AsyncSessionLocal, engine
from config import settings
from constants import DEFAULT_ROLES
from sqlalchemy import select
from services.provisioning import sync_user_store_role
from services.role_scope import find_role
from models.users import UserStoreRole
from passlib.context import CryptContext

import argparse
import asyncio
import sys
import uuid

# ── make sure backend/ is on sys.path so local imports resolve ────────────────
import os
sys.path.insert(0, os.path.dirname(__file__))


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Default credentials (override with CLI flags) ─────────────────────────────
DEFAULT_EMAIL = "admin@pharmacare.com"
DEFAULT_PASSWORD = "Admin@123"
DEFAULT_NAME = "Admin User"

# ── Role permission matrices ──────────────────────────────────────────────────
# Sourced from constants.DEFAULT_ROLES — the same list services/provisioning.py
# uses for every real pharmacy signup. This file used to keep its own separate
# dict-shaped copy that silently drifted from it (e.g. missing "purchases:edit"
# for manager here while provisioning.py's version had it, and vice versa for
# other permissions) — one seed path a pharmacy actually gets could differ from
# the other depending on which script happened to create it. Single source now.


async def seed(email: str, password: str, name: str, force: bool = False) -> None:
    async with AsyncSessionLocal() as db:

        # ── 1. Pharmacy ───────────────────────────────────────────────────────
        result = await db.execute(select(Pharmacy).limit(1))
        pharmacy = result.scalar_one_or_none()

        if pharmacy:
            print(f"  ✅ Pharmacy already exists: {pharmacy.name}  (id={pharmacy.id})")
        else:
            pharmacy = Pharmacy(
                id=uuid.uuid4(),
                name="PharmaCare Pharmacy",
                address="123 Medical Street",
                city="Bengaluru",
                state="Karnataka",
                pincode="560001",
                phone="9876543210",
                email="contact@pharmacare.com",
                gstin="29ABCDE1234F1Z5",
                drug_license_number="KA-BLR-12345",
            )
            db.add(pharmacy)
            await db.flush()          # get pharmacy.id before FK references
            print(f"  ✨ Created Pharmacy: {pharmacy.name}  (id={pharmacy.id})")

        # ── 2. PharmacySettings ───────────────────────────────────────────────
        stg_result = await db.execute(
            select(PharmacySettings).where(PharmacySettings.pharmacy_id == pharmacy.id)
        )
        if stg_result.scalar_one_or_none():
            print("  ✅ PharmacySettings already exist — skipping")
        else:
            db.add(PharmacySettings(
                id=uuid.uuid4(),
                pharmacy_id=pharmacy.id,
                bill_prefix="INV",
                bill_sequence_number=1,
                bill_number_length=6,
                low_stock_threshold_days=30,
                near_expiry_threshold_days=90,
                default_gst_rate=5.00,
                print_logo=True,
                print_drug_license=True,
                print_patient_name=True,
            ))
            print("  ✨ Created PharmacySettings")

        # ── 3. Roles ──────────────────────────────────────────────────────────
        role_map: dict[str, Role] = {}
        for role_def in DEFAULT_ROLES:
            role_name = role_def["name"]
            existing_role = await find_role(db, pharmacy.id, role_name, active_only=False)
            if existing_role:
                role_map[role_name] = existing_role
                print(f"  ✅ Role '{role_name}' already exists — skipping")
            else:
                new_role = Role(
                    id=uuid.uuid4(),
                    pharmacy_id=pharmacy.id,
                    chain_id=pharmacy.chain_id,
                    name=role_name,
                    description=role_def.get("display_name", role_name),
                    is_system_role=role_def.get("is_default", True),
                    permissions=role_def["permissions"],
                    is_active=True,
                )
                db.add(new_role)
                await db.flush()
                role_map[role_name] = new_role
                print(f"  ✨ Created role: {role_name}")

        # ── 4. Admin user ─────────────────────────────────────────────────────
        u_result = await db.execute(
            select(User).where(User.pharmacy_id == pharmacy.id, User.email == email)
        )
        existing_user = u_result.scalar_one_or_none()

        if existing_user:
            if force:
                existing_user.password_hash = pwd_context.hash(password)
                existing_user.name = name
                existing_user.is_active = True
                print(f"  🔄 Reset password for existing user '{email}'  (name updated to '{name}')")
            else:
                print(f"  ✅ Admin user '{email}' already exists — skipping")
                print("     Run with --force to reset the password to the default.")
            # Repair an admin created before this script wrote the store-access row.
            has_row = (await db.execute(select(UserStoreRole).where(
                UserStoreRole.user_id == existing_user.id,
                UserStoreRole.pharmacy_id == pharmacy.id))).scalar_one_or_none()
            if not has_row:
                await sync_user_store_role(
                    db, user_id=existing_user.id, pharmacy_id=pharmacy.id, role_id=existing_user.role_id)
                print("  🔧 Added the missing store-access row for this admin")
        else:
            admin_role = role_map.get("admin")
            if not admin_role:
                print("  ❌  Could not find 'admin' role — aborting user creation")
                return

            new_user = User(
                id=uuid.uuid4(),
                pharmacy_id=pharmacy.id,
                role_id=admin_role.id,
                is_admin=True,
                name=name,
                email=email,
                password_hash=pwd_context.hash(password),
                is_active=True,
            )
            db.add(new_user)
            await db.flush()
            # Every user-creation path writes the matching store-access row (docs/26) — without it the
            # sidebar store switcher and "Works at" lists come up empty for this admin.
            await sync_user_store_role(db, user_id=new_user.id, pharmacy_id=pharmacy.id, role_id=admin_role.id)
            print(f"  ✨ Created admin user: {name} <{email}>")

        await db.commit()

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("─" * 55)
    print("  LOGIN CREDENTIALS")
    print("─" * 55)
    print("  URL      : http://localhost:3000")
    print(f"  Email    : {email}")
    print(f"  Password : {password}")
    print("─" * 55)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PharmaCare PostgreSQL admin user")
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Admin email (default: {DEFAULT_EMAIL})")
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Admin password (default: {DEFAULT_PASSWORD})")
    parser.add_argument(
        "--name",
        default=DEFAULT_NAME,
        help=f"Admin display name (default: {DEFAULT_NAME})")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reset password/name even if user already exists")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print("  PharmaCare — Database Seed")
    print(f"  DB : {settings.DATABASE_URL}")
    print("=" * 55)
    print()

    try:
        await seed(args.email, args.password, args.name, force=args.force)
        print()
        print("  ✅  Seed complete. Start the backend and log in!")
        print()
    except Exception as exc:
        print(f"\n  ❌  Seed failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
