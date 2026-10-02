"""Patient Billing module (docs/29_BILLING_SCOPE.md) — one account per patient.
Every module (EMR, lab, IPD, pharmacy mirror) posts CHARGES; each counter
invoices and collects its own; the billing desk sees everything owed.

Independence rule (docs/27 product principle): nothing in here imports EMR or
pharmacy tables. The patient is referenced by id plus a name/UHID snapshot
taken when the charge is posted. Other modules call only `service.py`."""
