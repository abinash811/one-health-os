"""Shared dependencies for all routers — SQLAlchemy async session."""
from __future__ import annotations

from fastapi import Depends

from database import get_db, AsyncSessionLocal, engine  # noqa: F401 — re-exported for routers

# The database session every endpoint uses. `scope="function"` is REQUIRED: without it FastAPI (0.118+)
# sends the response BEFORE get_db's commit runs, so a client could be told "saved" before the data was
# committed — and a failed commit would never reach the client. With it, the commit finishes first.
# Always use `db: AsyncSession = DbSession`, never `Depends(get_db)` (scripts/check_db_session_scope.py).
DbSession = Depends(get_db, scope="function")

__all__ = ["get_db", "DbSession", "AsyncSessionLocal", "engine"]
