"""Database configuration tests."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.config import Settings
from app.database import create_db_engine, get_engine, init_db, reset_db_state
from app.models import Base


def test_create_engine_sqlite_enables_foreign_keys(settings):
    reset_db_state()
    engine = create_db_engine(settings)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert result == 1
    engine.dispose()


def test_init_db_registers_global_engine(settings):
    reset_db_state()
    engine = init_db(settings)
    assert get_engine() is engine
    reset_db_state()


def test_metadata_matches_expected_tables(settings):
    reset_db_state()
    engine = init_db(settings)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "companies",
        "leads",
        "agent_runs",
        "approvals",
        "approval_events",
        "outreaches",
        "outbound_messages",
        "daily_metrics",
        "workflow_executions",
        "business_reports",
        "notification_records",
    }.issubset(tables)
    reset_db_state()


def test_postgresql_url_is_default_production_shape():
    settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/ai_business_os"
    )
    assert settings.database_url.startswith("postgresql+psycopg://")
