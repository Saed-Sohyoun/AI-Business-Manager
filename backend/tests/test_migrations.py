"""Alembic migration script validation (no live PostgreSQL required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"


def test_alembic_config_loads():
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert "0001_initial_schema" in revisions
    assert "0002_research_memory" in revisions
    assert "0003_company_scores" in revisions
    assert "0004_company_audits" in revisions
    assert "0005_manager_orchestration" in revisions
    assert "0006_approval_system" in revisions
    assert "0007_sales_outreaches" in revisions
    assert "0008_outbound_messages" in revisions
    assert "0009_follow_ups" in revisions
    assert "0010_delivery_system" in revisions
    assert "0011_finance_ledger" in revisions
    assert "0012_business_reports" in revisions
    assert "0013_notifications" in revisions
    assert "0014_workflow_executions" in revisions
    assert "0015_security_events_webhooks" in revisions
    assert "0016_owner_control_plane" in revisions
    assert "0017_wave4_production_readiness" in revisions
    assert "0018_wave5_pilot_experiment" in revisions
    assert script.get_current_head() == "0018_wave5_pilot_experiment"


def test_initial_migration_module_exports_upgrade_downgrade():
    path = VERSIONS_DIR / "0001_initial_schema.py"
    assert path.exists()
    spec = importlib.util.spec_from_file_location("migration_0001", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.upgrade)
    assert callable(module.downgrade)
    assert module.down_revision is None


def test_migration_upgrade_against_sqlite(settings, monkeypatch):
    """Apply the initial migration online against SQLite for structural validation."""
    from alembic import command

    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    from app.config import clear_settings_cache

    clear_settings_cache()

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    # Point Alembic at sqlite for this validation run
    cfg.set_main_option("sqlalchemy.url", settings.database_url)

    # env.py reads Settings; ensure cache sees sqlite URL
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    # In-memory SQLite with Alembic needs a file-backed DB so connections share state
    db_path = BACKEND_ROOT / "tests" / "_migration_validation.sqlite"
    if db_path.exists():
        db_path.unlink()
    url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    clear_settings_cache()

    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        clear_settings_cache()
        if db_path.exists():
            db_path.unlink()
