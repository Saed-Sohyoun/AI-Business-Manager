from fastapi import APIRouter

from app.config import settings
from app.database import check_database_connection, configured_dialect

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    connected = check_database_connection()
    return {
        "status": "ok" if connected else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": {
            "configured": settings.database_is_configured(),
            "connected": connected,
            "dialect": configured_dialect(),
        },
    }
