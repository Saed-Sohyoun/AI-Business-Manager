"""Pytest configuration and shared fixtures.

Tests use an isolated SQLite database so Phase 1 validation does not
require a running PostgreSQL instance. Production remains PostgreSQL.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Ensure backend package imports resolve when pytest is launched from repo root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Must be set before app.config is imported by application modules
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_DEBUG", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def settings():
    from app.config import Settings, clear_settings_cache

    clear_settings_cache()
    cfg = Settings(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        n8n_webhook_require_signature=False,
        n8n_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
        health_rate_limit_per_minute=10_000,
    )
    yield cfg
    clear_settings_cache()


@pytest.fixture()
def app(settings):
    from app.config import clear_settings_cache
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clear_settings_cache()
    reset_db_state()
    application = create_app(settings)
    engine = init_db(settings)
    Base.metadata.create_all(bind=engine)
    yield application
    reset_db_state()
    clear_settings_cache()


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(settings) -> Generator[Session, None, None]:
    from app.database import get_session_factory, init_db, reset_db_state
    from app.models import Base

    reset_db_state()
    engine = init_db(settings)
    Base.metadata.create_all(bind=engine)
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
        reset_db_state()
