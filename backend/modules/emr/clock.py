"""What "today" and "now" mean for a clinic's appointments.

Booking rules ("no past dates, no slot that has already started") must use the clinic's own clock, not whatever
timezone the server happens to run in — a cloud server on UTC is 5½ hours behind an Indian clinic, so for the
first hours of every Indian morning "today" would be yesterday. The product is built for India, so one fixed
zone is used; a per-clinic timezone setting is a later step if the product leaves India."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")


def clinic_now() -> datetime:
    return datetime.now(CLINIC_TIMEZONE)


def clinic_today() -> date:
    return clinic_now().date()
