"""Health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import Settings, get_settings
from app.database import create_db_engine
from app.middleware.request_id import get_request_id
from app.schemas.common import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _check_database(settings: Settings) -> str:
    """Return database connectivity status without raising to the client.

    Uses a short-lived engine so a down database cannot exhaust the app pool
    or hang beyond `database_connect_timeout`.
    """
    probe = create_db_engine(settings)
    try:
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 — health must never crash the process
        logger.warning(
            "Database health check failed: %s",
            exc,
            extra={"request_id": "-"},
        )
        return "unavailable"
    finally:
        probe.dispose()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Process liveness with a fail-fast database signal.

    The process remains up even when the database is unavailable; clients
    can inspect the `database` field for readiness. Database probing uses
    `database_connect_timeout` so this endpoint does not hang.
    """
    cfg: Settings = getattr(request.app.state, "settings", None) or get_settings()
    db_status = _check_database(cfg)
    overall = "ok" if db_status == "ok" else "degraded"

    # Phase 20: slim production health — avoid env/version fingerprinting.
    if cfg.is_production:
        return HealthResponse(
            status=overall,
            service="ai-business-os",
            database=db_status,
            request_id=get_request_id(request),
        )

    return HealthResponse(
        status=overall,
        service=cfg.app_name,
        version=cfg.app_version,
        environment=cfg.app_env,
        database=db_status,
        request_id=get_request_id(request),
    )
