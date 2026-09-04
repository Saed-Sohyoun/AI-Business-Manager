"""FastAPI application entrypoint for the AI Business Operating System."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router, owner_router, pilot_router
from app.api.exception_handlers import register_exception_handlers
from app.api.n8n import router as n8n_router
from app.config import Settings, get_settings
from app.database import init_db, reset_db_state
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestIdMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.security import assert_production_settings

logger = get_logger(__name__)

# Explicit CORS headers — avoid allow_headers=["*"] with credentials.
_CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Request-ID",
    "X-N8N-Webhook-Secret",
    "X-N8N-Timestamp",
    "X-Owner-API-Key",
    "X-Owner-Resolver",
    "X-CSRF-Token",
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory — used by uvicorn and tests."""
    cfg = settings or get_settings()
    assert_production_settings(cfg)
    configure_logging(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "Starting %s v%s env=%s db=%s",
            cfg.app_name,
            cfg.app_version,
            cfg.app_env,
            cfg.masked_database_url(),
        )
        # Initialize engine at startup; do not require external AI providers.
        init_db(cfg)
        yield
        logger.info("Shutting down %s", cfg.app_name)
        reset_db_state()

    application = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        debug=cfg.app_debug and not cfg.is_production,
        lifespan=lifespan,
        docs_url=None if cfg.is_production else "/docs",
        redoc_url=None if cfg.is_production else "/redoc",
        openapi_url=None if cfg.is_production else "/openapi.json",
    )

    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(RateLimitMiddleware)
    if cfg.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=_CORS_ALLOW_HEADERS,
            expose_headers=["X-Request-ID"],
        )

    register_exception_handlers(application)
    # Health and future versioned routes; /health stays at root for probes.
    application.include_router(api_router)
    application.include_router(owner_router, prefix=cfg.api_prefix)
    application.include_router(pilot_router, prefix=cfg.api_prefix)
    application.include_router(n8n_router, prefix=cfg.api_prefix)

    application.state.settings = cfg
    return application


app = create_app()
