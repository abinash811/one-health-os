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

# Allowed status moves. Cancelling needs a reason; completed/cancelled/no_show are final.
APPOINTMENT_TRANSITIONS = {
    APPT_BOOKED: (APPT_CHECKED_IN, APPT_CANCELLED, APPT_NO_SHOW),
    APPT_CHECKED_IN: (APPT_IN_CONSULT, APPT_CANCELLED),
    APPT_IN_CONSULT: (APPT_COMPLETED,),
    APPT_COMPLETED: (),
    APPT_CANCELLED: (),
    APPT_NO_SHOW: (),
}

# A "doctor" is a login user; this default role name marks them in the doctor list.
ROLE_DOCTOR = "doctor"
ROLE_RECEPTIONIST = "receptionist"

MIN_SLOT_MINUTES = 5
MAX_SLOT_MINUTES = 120

# Prescription lifecycle: a doctor edits a draft freely; issuing makes it final
# (printable, immutable). A cancelled Rx frees the appointment for a replacement.
RX_DRAFT = "draft"
RX_ISSUED = "issued"
RX_CANCELLED = "cancelled"
PRESCRIPTION_STATUSES = (RX_DRAFT, RX_ISSUED, RX_CANCELLED)
RX_NUMBER_PREFIX = "RX-"

# ── Clinic settings (docs/28_EMR_SCOPE.md → Settings) ────────────────────────
FIELD_HIDDEN = "hidden"
FIELD_OPTIONAL = "optional"
FIELD_REQUIRED = "required"
FIELD_STATES = (FIELD_HIDDEN, FIELD_OPTIONAL, FIELD_REQUIRED)

# Patient-form fields a clinic can hide or require. `name` is always required
# and is deliberately not configurable. Defaults match the pre-settings form.
PATIENT_FORM_DEFAULTS = {
    "phone": FIELD_OPTIONAL, "alternate_phone": FIELD_OPTIONAL,
    "age": FIELD_OPTIONAL, "date_of_birth": FIELD_OPTIONAL,
    "gender": FIELD_OPTIONAL, "blood_group": FIELD_OPTIONAL,
    "city": FIELD_OPTIONAL, "allergies": FIELD_OPTIONAL, "notes": FIELD_OPTIONAL,
}
DEFAULT_RX_PREFIX = "RX-"
DEFAULT_UHID_PREFIX = "UH-"
DEFAULT_UHID_DIGITS = 6
DEFAULT_SLOT_MINUTES = 15
