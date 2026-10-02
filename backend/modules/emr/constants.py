"""EMR domain constants — every status/type string used by the EMR module
lives here, never as a raw literal elsewhere (Manifesto rule 9)."""

# Appointment lifecycle: booked -> checked_in -> in_consult -> completed,
# with cancelled / no_show as terminal side exits.
APPT_BOOKED = "booked"
APPT_CHECKED_IN = "checked_in"
APPT_IN_CONSULT = "in_consult"
APPT_COMPLETED = "completed"
APPT_CANCELLED = "cancelled"
APPT_NO_SHOW = "no_show"
APPOINTMENT_STATUSES = (
    APPT_BOOKED, APPT_CHECKED_IN, APPT_IN_CONSULT,
    APPT_COMPLETED, APPT_CANCELLED, APPT_NO_SHOW,
)

# A visit is either booked for a slot, or a walk-in that only gets a token.
APPT_TYPE_SCHEDULED = "scheduled"
APPT_TYPE_WALK_IN = "walk_in"
APPOINTMENT_TYPES = (APPT_TYPE_SCHEDULED, APPT_TYPE_WALK_IN)

# Where a patient record was first created — drives the "Added in ..." badge.
PATIENT_SOURCE_EMR = "emr"
PATIENT_SOURCE_PHARMACY = "pharmacy"
PATIENT_SOURCES = (PATIENT_SOURCE_EMR, PATIENT_SOURCE_PHARMACY)
