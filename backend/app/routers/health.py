"""Health checks.

`/health` is deliberately unauthenticated and detail-free — it is for load
balancers and uptime monitors, which have no API key. `/api/health` sits behind
the API key and reports what is actually reachable, which is the endpoint to hit
when the UI says "can't reach the database" and you want to know why.
"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.config import OPENAI_API_KEY, PINECONE_API_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.database import engine

logger = logging.getLogger("app")

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness() -> dict:
    """Is the process up? Says nothing about its dependencies."""
    return {"status": "ok"}


@router.get("/api/health")
def readiness() -> dict:
    """Is the app actually able to serve requests? Never raises — a health check
    that 500s tells you less than one that reports which dependency is down."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        logger.warning("health_db_unreachable error=%s", exc)
        database = "unreachable"

    checks = {
        "database": database,
        "storage": "configured" if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else "not_configured",
        "openai": "configured" if OPENAI_API_KEY else "not_configured",
        "pinecone": "configured" if PINECONE_API_KEY else "not_configured",
    }
    return {"status": "ok" if database == "ok" else "degraded", "checks": checks}
