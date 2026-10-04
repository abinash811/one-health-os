from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database import AsyncSessionLocal
from models.pharmacy import Pharmacy
from routers import (
    auth, batches, billing, chains, clinic_access, clinic_doctors, clinics, customers, inventory, practitioners,
    purchase_returns, purchases, reports, sales_returns,
    settings, stock_transfers, suppliers, users,
)
import modules.emr.clinic_guard  # noqa: F401  (registers EMR's say in switching a clinic off)
import modules.patient_billing.clinic_guard  # noqa: F401
from modules.emr.routers import appointments as emr_appointments
from modules.emr.routers import patients as emr_patients
from modules.emr.routers import prescriptions as emr_prescriptions
from modules.emr.routers import schedules as emr_schedules
from modules.emr.routers import settings as emr_settings
from modules.patient_billing.routers import accounts as pb_accounts
from modules.patient_billing.routers import charges as pb_charges
from modules.patient_billing.routers import invoices as pb_invoices
from services.provisioning import create_pharmacy_with_defaults
from utils import excel

app = FastAPI(title="PharmaCare API", version="2.0.0")
logger = logging.getLogger(__name__)


# ── Global exception handler ─────────────────────────────────────────────────
# Catches anything a router didn't wrap in HTTPException — an unguarded
# uuid.UUID() call, a KeyError, whatever — and turns it into a clean JSON 500
# instead of a raw traceback reaching the client. Does NOT intercept
# HTTPException or FastAPI's own RequestValidationError; those already have
# their own more-specific handlers and keep returning their real status codes.
# docs/12_ERROR_HANDLING.md described this as already existing — it wasn't;
# this is that gap closed for real, added August 22, 2026.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )

_raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip() and o.strip() != "*"]
if not _origins:
    raise RuntimeError(
        "CORS_ORIGINS must be set to an explicit origin list — '*' is not allowed with credentials."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chains.router)
app.include_router(settings.router)
app.include_router(inventory.router)
app.include_router(batches.router)
app.include_router(billing.router)
app.include_router(customers.router)
app.include_router(practitioners.router)
app.include_router(reports.router)
app.include_router(suppliers.router)
app.include_router(purchases.router)
app.include_router(purchase_returns.router)
app.include_router(sales_returns.router)
app.include_router(stock_transfers.router)
app.include_router(excel.router)
app.include_router(emr_patients.router)
app.include_router(emr_schedules.router)
app.include_router(emr_appointments.router)
app.include_router(emr_prescriptions.router)
app.include_router(emr_settings.router)
app.include_router(clinics.router)
app.include_router(clinic_access.router)
app.include_router(clinic_doctors.router)
app.include_router(pb_charges.router)
app.include_router(pb_accounts.router)
app.include_router(pb_invoices.router)


# ── Startup seeder ────────────────────────────────────────────────────────────
# Ensures at least one pharmacy exists on a totally fresh database, so local
# dev / CI never starts with an empty DB. Real signups create their own
# pharmacy via POST /auth/register — this only runs once, on an empty DB.

@app.on_event("startup")
async def seed_defaults() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            pharm_result = await db.execute(select(Pharmacy).limit(1))
            if pharm_result.scalar_one_or_none():
                return

            pharmacy = await create_pharmacy_with_defaults(
                db,
                name="PharmaCare",
                address="123 Main Street",
                city="Bangalore",
                state="Karnataka",
                pincode="560001",
                phone="9999999999",
            )
            print(f"[seed] Created default pharmacy: {pharmacy.id}")

    print("PharmaCare PostgreSQL backend started — database seeded ✓")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
