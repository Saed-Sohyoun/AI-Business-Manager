"""HTTP API routers."""

from fastapi import APIRouter

from app.api import health
from app.api.pilot import router as pilot_router

api_router = APIRouter()
api_router.include_router(health.router)

__all__ = ["api_router", "pilot_router"]
