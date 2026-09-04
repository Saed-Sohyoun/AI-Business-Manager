"""Wave 5 — readiness, budget warnings, drills, experiment, secret scan."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings, clear_settings_cache
from app.exceptions import ForbiddenError, LimitReachedError, ServiceUnavailableError
from app.models.owner_alert import OwnerAlert
from app.models.system_mode import AlertPriority, SystemMode
from app.owner.controls import SystemControlService
from app.owner.readiness import ReadinessService
from app.owner.schemas_pilot import PilotExperimentCreate
from app.pilot.budget import BudgetGuard
from app.pilot.budget_warnings import emit_budget_threshold_alerts
from app.pilot.config import pilot_mode_from_settings
from app.pilot.experiment import PilotExperimentService
from app.providers.circuit_breaker import CircuitBreaker, CircuitState, reset_circuits
from app.security import assert_production_settings


OWNER_KEY = "wave5-owner-key-secret"


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        owner_api_key=SecretStr(OWNER_KEY),
        n8n_webhook_secret=SecretStr("wave5-n8n-secret"),
        n8n_webhook_require_signature=False,
        n8n_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
        health_rate_limit_per_minute=10_000,
        allow_production_mode=False,
        operating_mode="pilot",
        daily_budget_limit=Decimal("3.00"),
        max_single_expense=Decimal("20.00"),
        budget_warning_ratio=Decimal("0.70"),
        budget_urgent_ratio=Decimal("0.90"),
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def w5_settings(settings):
    return settings.model_copy(
        update={
            "owner_api_key": SecretStr(OWNER_KEY),
            "n8n_webhook_secret": SecretStr("wave5-n8n-secret"),
            "approval_authorized_resolvers": "owner,admin",
            "budget_warning_ratio": Decimal("0.70"),
            "budget_urgent_ratio": Decimal("0.90"),
        }
    )


@pytest.fixture()
def w5_app(w5_settings):
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clear_settings_cache()
    reset_db_state()
    application = create_app(w5_settings)
    engine = init_db(w5_settings)
    Base.metadata.create_all(bind=engine)
    yield application
    reset_db_state()
    clear_settings_cache()


@pytest.fixture()
def w5_client(w5_app):
    from fastapi.testclient import TestClient

    with TestClient(w5_app) as client:
        yield client


def _headers() -> dict[str, str]:
    return {"X-Owner-API-Key": OWNER_KEY, "X-Owner-Resolver": "owner"}


def test_readiness_not_ready_on_sqlite_and_concurrency_unset(w5_settings, monkeypatch):
    monkeypatch.delenv("POSTGRES_CONCURRENCY_PASS", raising=False)
    monkeypatch.delenv("BACKUP_RESTORE_PASS", raising=False)
    view = ReadinessService(w5_settings).evaluate()
    assert view.overall == "NOT_READY"
    assert view.production_locked is True
    by_id = {c.id: c for c in view.checks}
    assert by_id["database"].status == "fail"
    assert by_id["concurrency_suite"].status == "fail"
    assert by_id["backup_status"].status == "fail"
    blob = view.model_dump_json()
    assert OWNER_KEY not in blob
    assert "wave5-n8n-secret" not in blob


def test_readiness_endpoint_requires_owner(w5_client, monkeypatch):
    monkeypatch.delenv("POSTGRES_CONCURRENCY_PASS", raising=False)
    denied = w5_client.get("/api/v1/owner/readiness")
    assert denied.status_code in {401, 403}
    ok = w5_client.get("/api/v1/owner/readiness", headers=_headers())
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["overall"] == "NOT_READY"
    assert data["production_locked"] is True


def test_budget_warning_thresholds(db_session, settings):
    cfg = settings.model_copy(
        update={
            "daily_budget_limit": Decimal("10.00"),
            "max_single_expense": Decimal("20.00"),
            "budget_warning_ratio": Decimal("0.70"),
            "budget_urgent_ratio": Decimal("0.90"),
        }
    )
    pilot = pilot_mode_from_settings(cfg)

    emit_budget_threshold_alerts(
        db_session,
        spent=Decimal("6.00"),
        limit=Decimal("10.00"),
        currency="EUR",
        ratio=Decimal("0.60"),
        pilot=pilot,
        commit=True,
    )
    assert db_session.scalar(select(OwnerAlert.id).limit(1)) is None

    emit_budget_threshold_alerts(
        db_session,
        spent=Decimal("7.00"),
        limit=Decimal("10.00"),
        currency="EUR",
        ratio=Decimal("0.70"),
        pilot=pilot,
        commit=True,
    )
    warns = db_session.scalars(
        select(OwnerAlert).where(OwnerAlert.dedupe_key.like("pilot-budget-warning-%"))
    ).all()
    assert len(warns) == 1
    assert warns[0].priority in {AlertPriority.INFO.value, AlertPriority.IMPORTANT.value}

    emit_budget_threshold_alerts(
        db_session,
        spent=Decimal("9.00"),
        limit=Decimal("10.00"),
        currency="EUR",
        ratio=Decimal("0.90"),
        pilot=pilot,
        commit=True,
    )
    urgents = db_session.scalars(
        select(OwnerAlert).where(OwnerAlert.dedupe_key.like("pilot-budget-urgent-%"))
    ).all()
    assert len(urgents) == 1
    assert urgents[0].priority == AlertPriority.URGENT.value

    emit_budget_threshold_alerts(
        db_session,
        spent=Decimal("9.50"),
        limit=Decimal("10.00"),
        currency="EUR",
        ratio=Decimal("0.95"),
        pilot=pilot,
        commit=True,
    )
    urgents2 = db_session.scalars(
        select(OwnerAlert).where(OwnerAlert.dedupe_key.like("pilot-budget-urgent-%"))
    ).all()
    assert len(urgents2) == 1

    guard = BudgetGuard(db_session, cfg)
    with pytest.raises(LimitReachedError):
        guard.assert_can_spend(Decimal("10.01"))


def test_kill_switch_pause_all_blocks_outbound_and_ai(db_session):
    controls = SystemControlService(db_session)
    controls.pause_all(actor="owner", reason="wave5 drill")
    with pytest.raises(ForbiddenError):
        controls.assert_ai_operations(actor="system")
    with pytest.raises(ForbiddenError):
        controls.assert_outbound(actor="system")
    state = controls.get_or_create()
    assert state.system_mode == SystemMode.PAUSED_BY_OWNER.value
    assert state.ai_operations_enabled is False
    assert state.outbound_enabled is False


def test_safe_mode_drill(db_session):
    controls = SystemControlService(db_session)
    controls.enter_safe_mode(reason="wave5 safe mode drill", actor="owner")
    state = controls.get_or_create()
    assert state.system_mode == SystemMode.SAFE_MODE.value
    with pytest.raises(ForbiddenError):
        controls.assert_outbound(actor="system")
    with pytest.raises(ForbiddenError):
        controls.assert_spending(actor="system")


def test_circuit_open_surfaces_circuit_open_code():
    reset_circuits()
    cb = CircuitBreaker(name="wave5-test", failure_threshold=1, reset_timeout_seconds=60)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    with pytest.raises(ServiceUnavailableError) as excinfo:
        cb.call(lambda: True)
    assert excinfo.value.details.get("code") == "CIRCUIT_OPEN"


def test_production_remains_locked():
    cfg = _settings()
    assert cfg.allow_production_mode is False
    assert cfg.is_pilot_mode is True
    with pytest.raises(Exception):
        Settings(
            app_env="test",
            operating_mode="production",
            allow_production_mode=False,
            database_url="sqlite+pysqlite:///:memory:",
        )
    assert_production_settings(cfg)


def test_experiment_niche_requires_approval(db_session, settings):
    svc = PilotExperimentService(db_session, settings)
    draft = svc.create_draft(
        PilotExperimentCreate(niche="dental clinics NL", geography="NL", language="nl")
    )
    assert draft.owner_approved_niche is False
    assert draft.status == "draft"

    with pytest.raises(ForbiddenError) as excinfo:
        svc.activate(draft.id)
    assert excinfo.value.details.get("code") == "NICHE_APPROVAL_REQUIRED"

    approved = svc.approve_niche(draft.id, actor="owner")
    assert approved.owner_approved_niche is True
    assert approved.status == "active"


def test_secret_scan_importable_and_clean_without_dist():
    import importlib.util
    import tempfile

    path = Path(__file__).resolve().parents[1] / "scripts" / "secret_scan.py"
    spec = importlib.util.spec_from_file_location("secret_scan_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with tempfile.TemporaryDirectory() as tmp:
        results = mod.scan([Path(tmp)])
        assert all(v == "NOT_FOUND" for v in results.values())
        code = mod.main(["--root", tmp])
        assert code == 0

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assert isinstance(dist.exists(), bool)
