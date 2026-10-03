"""Read-only preview of what `alembic upgrade head` will do for doctors (docs/31_CORE_DOCTOR_SCOPE.md).

Run BEFORE the migration:  python practitioners_dry_run.py
It changes nothing. It lists every login that will become a doctor profile (role `doctor`, or an EMR
profile, schedule, appointment or prescription pointing at them) so you can see exactly who is affected.
"""
import asyncio
import logging

from sqlalchemy import text

from database import AsyncSessionLocal

QUERY = """
SELECT u.name, u.email, r.name AS role,
  (SELECT count(*) FROM emr_doctor_profiles p WHERE p.user_id = u.id) AS profiles,
  (SELECT count(*) FROM emr_doctor_schedules s WHERE s.doctor_user_id = u.id AND s.deleted_at IS NULL) AS schedules,
  (SELECT count(*) FROM emr_appointments a WHERE a.doctor_user_id = u.id) AS appointments,
  (SELECT count(*) FROM emr_prescriptions x WHERE x.doctor_user_id = u.id) AS prescriptions
FROM users u JOIN roles r ON r.id = u.role_id
WHERE r.name = 'doctor'
   OR EXISTS (SELECT 1 FROM emr_doctor_profiles p WHERE p.user_id = u.id)
   OR EXISTS (SELECT 1 FROM emr_doctor_schedules s WHERE s.doctor_user_id = u.id AND s.deleted_at IS NULL)
   OR EXISTS (SELECT 1 FROM emr_appointments a WHERE a.doctor_user_id = u.id)
   OR EXISTS (SELECT 1 FROM emr_prescriptions x WHERE x.doctor_user_id = u.id)
ORDER BY u.name
"""


async def main() -> None:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(QUERY))).all()
    print(f"{'NAME':28} {'EMAIL':32} {'ROLE':14} PROFILE SCHED APPTS RX")
    for name, email, role, prof, sched, appts, rx in rows:
        print(f"{name[:27]:28} {email[:31]:32} {role[:13]:14} {prof:7} {sched:5} {appts:5} {rx:2}")
    print(f"\n{len(rows)} login(s) will each become a doctor profile (linked to that login). Nothing was changed.")


if __name__ == "__main__":
    asyncio.run(main())
