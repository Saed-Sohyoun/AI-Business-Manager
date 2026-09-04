"""Phase 21 — cross-cutting QA: validation, concurrency, lifespan, budgets, E2E."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import inspect, select

from app.approvals import ApprovalRequest, ApprovalService
from app.config import Settings, clear_settings_cache
from app.exceptions import ForbiddenError, UnauthorizedError
from app.models import WorkflowExecution
from app.models.enums import CostCategory, RiskLevel, WorkflowExecutionStatus, WorkflowName
from app.orchestration.schemas import WorkflowTriggerRequest
from app.orchestration.service import N8nOrchestrationService
from app.security import validate_webhook_timestamp
from app.security.rate_limit import http_rate_limiter


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        n8n_webhook_secret=SecretStr("qa-n8n-secret"),
        n8n_webhook_require_timestamp=False,
        n8n_default_timeout_seconds=30.0,
        n8n_max_execution_retries=2,
        n8n_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
        health_rate_limit_per_minute=10_000,
        max_single_expense=Decimal("25"),
        daily_budget_limit=Decimal("50"),
        approval_authorized_resolvers="owner,admin",
        max_agent_runtime_seconds=60,
        max_retries=2,
        max_tasks_per_run=20,
        max_ai_cost_per_run=Decimal("5.00"),
    )
    base.update(overrides)
    return Settings(**base)


# --- Invalid inputs -------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"idempotency_key": "   "},
        {"idempotency_key": "x" * 129},
        {"idempotency_key": "ok", "timeout_seconds": 4},
        {"idempotency_key": "ok", "timeout_seconds": 601},
        {"idempotency_key": "ok", "payload": []},
        {"idempotency_key": "ok", "unknown_field": 1},
    ],
)
def test_n8n_webhook_invalid_bodies_return_422(n8n_client_factory, body):
    client, _app = n8n_client_factory()
    resp = client.post(
        "/api/v1/n8n/webhooks/research",
        json=body,
        headers={"X-N8N-Webhook-Secret": "qa-n8n-secret", "Content-Type": "application/json"},
    )
    assert resp.status_code == 422


def test_idempotency_key_strips_whitespace():
    req = WorkflowTriggerRequest(idempotency_key="  key-1  ")
    assert req.idempotency_key == "key-1"
    with pytest.raises(ValidationError):
        WorkflowTriggerRequest(idempotency_key="   ")


# --- Soft timeout keeps success; stale RUNNING reclaim --------------------------


def test_soft_timeout_keeps_succeeded(db_session):
    cfg = _settings(n8n_default_timeout_seconds=5.0)
    calls = {"n": 0}

    def slow_ok(payload, timeout):
        calls["n"] += 1
        return {"ok": True, "late": True}

    # Simulate soft overrun without sleeping: patch monotonic around _run
    svc = N8nOrchestrationService(
        session=db_session,
        settings=cfg,
        handlers={WorkflowName.RESEARCH.value: slow_ok},
    )

    import app.orchestration.service as svc_mod

    times = iter([100.0, 120.0])  # started; elapsed check

    def fake_monotonic():
        try:
            return next(times)
        except StopIteration:
            return 120.0

    original = svc_mod.time.monotonic
    svc_mod.time.monotonic = fake_monotonic
    try:
        view = svc.trigger(
            WorkflowName.RESEARCH,
            WorkflowTriggerRequest(idempotency_key="soft-to-1", timeout_seconds=5),
        )
    finally:
        svc_mod.time.monotonic = original

    assert view.status == WorkflowExecutionStatus.SUCCEEDED
    assert view.result_summary.get("_soft_timeout") is True
    assert calls["n"] == 1

    # Replay must not re-execute
    again = svc.trigger(
        WorkflowName.RESEARCH,
        WorkflowTriggerRequest(idempotency_key="soft-to-1", timeout_seconds=5),
    )
    assert again.idempotent_replay is True
    assert calls["n"] == 1


def test_stale_running_reclaimed(db_session):
    cfg = _settings()
    handlers = {WorkflowName.RESEARCH.value: lambda p, t: {"reclaimed": True}}
    svc = N8nOrchestrationService(session=db_session, settings=cfg, handlers=handlers)
    row = WorkflowExecution(
        workflow_name=WorkflowName.RESEARCH,
        idempotency_key="stale-run-1",
        status=WorkflowExecutionStatus.RUNNING,
        attempt=1,
        timeout_seconds=5,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    db_session.add(row)
    db_session.commit()

    view = svc.trigger(
        WorkflowName.RESEARCH,
        WorkflowTriggerRequest(idempotency_key="stale-run-1"),
    )
    assert view.status == WorkflowExecutionStatus.SUCCEEDED
    assert view.attempt == 2
    assert view.result_summary.get("reclaimed") is True


# --- Concurrent idempotent finance ---------------------------------------------


def test_concurrent_cost_idempotency(tmp_path):
    from app.agents.finance import CostRecordRequest, FinanceAgent
    from app.approvals import ApprovalService
    from app.database import get_session_factory, init_db, reset_db_state
    from app.models import Base, CostEntry

    db_file = tmp_path / "qa_finance.sqlite"
    url = f"sqlite+pysqlite:///{db_file.as_posix()}"
    clear_settings_cache()
    reset_db_state()
    cfg = _settings(
        database_url=url,
        max_single_expense=Decimal("100"),
        daily_budget_limit=Decimal("1000"),
    )
    engine = init_db(cfg, force=True)
    Base.metadata.create_all(bind=engine)

    def worker():
        session = get_session_factory()()
        try:
            agent = FinanceAgent(
                session=session,
                settings=cfg,
                approval_service=ApprovalService(session, cfg),
            )
            entry = agent.record_cost(
                CostRecordRequest(
                    amount=Decimal("10"),
                    category=CostCategory.AI,
                    source="qa",
                    idempotency_key="concurrent-cost-1",
                )
            )
            return str(entry.id)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: worker(), range(8)))
    assert len(set(ids)) == 1

    session = get_session_factory()()
    try:
        rows = session.scalars(select(CostEntry)).all()
        assert len(rows) == 1
    finally:
        session.close()
        reset_db_state()
        clear_settings_cache()


# --- Approval bypass + budget + provider outage --------------------------------


def test_permission_and_approval_bypass_blocked(db_session):
    cfg = _settings()
    svc = ApprovalService(db_session, cfg)
    with pytest.raises(ForbiddenError):
        svc.assert_executable("sales.first_outreach")
    with pytest.raises(ForbiddenError):
        svc.request_approval(
            ApprovalRequest(
                action_type="finance.money_transfer",
                description="bypass",
                requested_by="manager",
                risk_level=RiskLevel.GREEN,
                action_payload={"amount": 1},
            )
        )


def test_budget_limit_blocks_finance(db_session):
    from app.agents.finance import CostRecordRequest, FinanceAgent
    from app.approvals import ApprovalService
    from app.exceptions import LimitReachedError

    cfg = _settings(max_single_expense=Decimal("10"), daily_budget_limit=Decimal("15"))
    agent = FinanceAgent(
        session=db_session,
        settings=cfg,
        approval_service=ApprovalService(db_session, cfg),
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("10"),
            category=CostCategory.AI,
            source="qa",
            idempotency_key="budget-a",
        )
    )
    with pytest.raises((ForbiddenError, LimitReachedError)):
        agent.record_cost(
            CostRecordRequest(
                amount=Decimal("10"),
                category=CostCategory.AI,
                source="qa",
                idempotency_key="budget-b",
            )
        )


def test_search_provider_outage_maps_error():
    from app.providers.search.exceptions import SearchProviderError
    from app.providers.search.tavily_provider import TavilySearchProvider
    from app.providers.search.types import SearchRequest

    class Boom:
        def post(self, *args, **kwargs):
            raise ConnectionError("provider down")

    provider = TavilySearchProvider(
        _settings(tavily_api_key=SecretStr("tvly-test"), tavily_max_retries=0),
        http_client=Boom(),
    )
    with pytest.raises(SearchProviderError):
        provider.search(SearchRequest(query="test"))


# --- Lifespan / init_db reuse ---------------------------------------------------


def test_init_db_reuses_engine_without_force(settings):
    from app.database import get_engine, init_db, reset_db_state

    reset_db_state()
    first = init_db(settings)
    second = init_db(settings)
    assert first is second
    assert get_engine() is first
    forced = init_db(settings, force=True)
    assert forced is not first
    reset_db_state()


def test_app_lifespan_startup_shutdown(settings):
    from fastapi.testclient import TestClient

    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base
    from app.security.rate_limit import http_rate_limiter

    http_rate_limiter.reset()
    clear_settings_cache()
    reset_db_state()
    cfg = _settings(
        database_url=settings.database_url,
        health_rate_limit_per_minute=10_000,
    )
    application = create_app(cfg)
    with TestClient(application) as client:
        # Schema after lifespan init
        Base.metadata.create_all(bind=init_db(cfg))
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] in {"ok", "degraded"}
    reset_db_state()
    clear_settings_cache()


def test_metadata_includes_workflow_executions(settings):
    from app.database import init_db, reset_db_state
    from app.models import Base

    reset_db_state()
    engine = init_db(settings)
    Base.metadata.create_all(bind=engine)
    tables = set(inspect(engine).get_table_names())
    assert "workflow_executions" in tables
    assert "business_reports" in tables
    assert "notification_records" in tables
    reset_db_state()


# --- Webhook timestamp future skew + rate limit ---------------------------------


def test_webhook_rejects_future_timestamp():
    now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    future = now + timedelta(seconds=400)
    with pytest.raises(UnauthorizedError):
        validate_webhook_timestamp(
            str(int(future.timestamp())),
            max_skew_seconds=300,
            now=now,
        )


def test_n8n_rate_limit_bucket(n8n_client_factory):
    http_rate_limiter.reset()
    client, app = n8n_client_factory(
        n8n_rate_limit_per_minute=2,
        health_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
    )
    headers = {"X-N8N-Webhook-Secret": "qa-n8n-secret", "Content-Type": "application/json"}
    r1 = client.post(
        "/api/v1/n8n/webhooks/research",
        json={"idempotency_key": "rl-1"},
        headers=headers,
    )
    r2 = client.post(
        "/api/v1/n8n/webhooks/research",
        json={"idempotency_key": "rl-2"},
        headers=headers,
    )
    r3 = client.post(
        "/api/v1/n8n/webhooks/research",
        json={"idempotency_key": "rl-3"},
        headers=headers,
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    http_rate_limiter.reset()


# --- E2E manager happy path with mocked specialists -----------------------------


def test_e2e_manager_research_score_cycle(db_session):
    from app.agents.manager import ManagerAgent, ManagerRequest, RegistryExecutor
    from app.agents.manager.schemas import DelegationResult

    cfg = _settings()
    registry = RegistryExecutor()
    registry.register(
        "research",
        "discover_companies",
        lambda p, t: DelegationResult(status="succeeded", summary="found", output={"companies_created": 2}),
    )
    registry.register(
        "scoring",
        "score_companies",
        lambda p, t: DelegationResult(status="succeeded", summary="scored", output={"scored": 2}),
    )
    agent = ManagerAgent(session=db_session, executor=registry, settings=cfg)
    result = agent.run(
        ManagerRequest(
            goal="Generate 2 qualified local business leads.",
            target_qualified_leads=2,
            location="Berlin",
        )
    )
    assert result.status == "succeeded"
    assert result.tasks_created >= 1


# --- Frontend format helpers present --------------------------------------------


def test_frontend_format_module_exists():
    root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "format.js"
    assert root.exists(), "frontend/src/lib/format.js must exist for dashboard build"
    text = root.read_text(encoding="utf-8")
    for name in ("formatMoney", "formatDateTime", "formatDate", "pct"):
        assert f"export function {name}" in text


# --- Fixture --------------------------------------------------------------------


@pytest.fixture()
def n8n_client_factory():
    from fastapi.testclient import TestClient

    from app.database import get_engine, init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clients: list[TestClient] = []

    def factory(**overrides):
        clear_settings_cache()
        reset_db_state()
        http_rate_limiter.reset()
        cfg = _settings(**overrides)
        application = create_app(cfg)
        application.state.n8n_handlers = {
            WorkflowName.RESEARCH.value: lambda p, t: {"ok": True},
            WorkflowName.AUDIT.value: lambda p, t: {"ok": True},
            WorkflowName.DAILY_CYCLE.value: lambda p, t: {"ok": True},
            WorkflowName.OUTREACH_APPROVAL_QUEUE.value: lambda p, t: {"ok": True},
            WorkflowName.FOLLOW_UPS.value: lambda p, t: {"ok": True},
            WorkflowName.DAILY_REPORT.value: lambda p, t: {"ok": True},
            WorkflowName.ERROR_MONITORING.value: lambda p, t: {"ok": True},
        }
        client = TestClient(application)
        client.__enter__()
        Base.metadata.create_all(bind=get_engine())
        clients.append(client)
        return client, application

    yield factory
    for client in clients:
        client.__exit__(None, None, None)
    reset_db_state()
    clear_settings_cache()
    http_rate_limiter.reset()
