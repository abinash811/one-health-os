"""EMR's say in switching a clinic off: no visit may still be waiting to happen."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.emr.constants import APPT_BOOKED, APPT_CHECKED_IN, APPT_IN_CONSULT
from modules.emr.models import EmrAppointment
from services.clinic_guards import register_clinic_guard


@register_clinic_guard
async def open_visits(db: AsyncSession, clinic_id: uuid.UUID) -> Optional[str]:
    n = (await db.execute(select(func.count()).select_from(EmrAppointment).where(
        EmrAppointment.clinic_id == clinic_id, EmrAppointment.deleted_at.is_(None),
        EmrAppointment.status.in_((APPT_BOOKED, APPT_CHECKED_IN, APPT_IN_CONSULT)),
        EmrAppointment.appointment_date >= date.today()))).scalar_one()
    if n:
        return f"{n} appointment{'s' if n != 1 else ''} from today onwards {'are' if n != 1 else 'is'} still open — " \
               "complete or cancel them first"
    return None
