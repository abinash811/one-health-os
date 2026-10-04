"""Things that must be finished before a clinic can be switched off (docs/32 P2d).

The clinic record lives in core; what counts as "open work" belongs to each module (EMR: upcoming visits,
Patient Billing: unpaid money). Modules register a guard here — core never reads their tables. A guard returns
a plain-language reason, or None when the clinic is clear."""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

ClinicGuard = Callable[[AsyncSession, uuid.UUID], Awaitable[Optional[str]]]
GUARDS: list[ClinicGuard] = []


def register_clinic_guard(guard: ClinicGuard) -> ClinicGuard:
    if guard not in GUARDS:
        GUARDS.append(guard)
    return guard


async def first_open_work(db: AsyncSession, clinic_id: uuid.UUID) -> Optional[str]:
    for guard in GUARDS:
        reason = await guard(db, clinic_id)
        if reason:
            return reason
    return None
