"""Patient Billing constants — single source for every status/enum value."""

# Where a charge came from
SRC_EMR = "emr"
SRC_LAB = "lab"
SRC_IPD = "ipd"
SRC_MANUAL = "manual"
SRC_PHARMACY = "pharmacy"
SOURCE_MODULES = (SRC_EMR, SRC_LAB, SRC_IPD, SRC_MANUAL, SRC_PHARMACY)
# Pharmacy items are billed ONLY by the pharmacy module (GST tax invoice, stock, H1):
# they may appear on the account as a mirror but can never go on a clinic invoice.
# Posting them is not open yet — it arrives with the pharmacy connector.
SOURCES_POSTABLE_NOW = (SRC_EMR, SRC_LAB, SRC_IPD, SRC_MANUAL)

# Charge lifecycle
CHG_UNBILLED = "unbilled"
CHG_INVOICED = "invoiced"
CHG_PAID = "paid"
CHG_VOID = "void"

# Invoice lifecycle
INV_ISSUED = "issued"
INV_PART_PAID = "part_paid"
INV_PAID = "paid"
INV_CANCELLED = "cancelled"
INVOICE_OPEN_STATUSES = (INV_ISSUED, INV_PART_PAID)

# Payment
PAY_CASH = "cash"
PAY_UPI = "upi"
PAY_CARD = "card"
PAYMENT_MODES = (PAY_CASH, PAY_UPI, PAY_CARD)

# Which counter issued an invoice (for day closing)
COUNTER_FRONT_DESK = "front_desk"
COUNTER_BILLING_DESK = "billing_desk"
COUNTER_LAB = "lab"
COUNTER_IPD = "ipd"
COUNTERS = (COUNTER_FRONT_DESK, COUNTER_BILLING_DESK, COUNTER_LAB, COUNTER_IPD)

# Numbering — max trailing number ever issued + 1, so numbers are never reused or restarted
INVOICE_PREFIX = "INV-"
RECEIPT_PREFIX = "RCT-"

# Account list filters
ACC_PENDING = "pending"
ACC_NOT_INVOICED = "not_invoiced"
ACC_INVOICED_UNPAID = "invoiced_unpaid"
ACC_PART_PAID = "part_paid"
ACC_ALL = "all"
ACCOUNT_FILTERS = (ACC_PENDING, ACC_NOT_INVOICED, ACC_INVOICED_UNPAID, ACC_PART_PAID, ACC_ALL)

MAX_AMOUNT_PAISE = 100_000_000  # ₹10 lakh per line / payment — guards typos
