"""Phase 17 — n8n orchestration webhooks, auth, idempotency, timeouts."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.approvals.schemas import ApprovalRequest
from app.approvals.service import ApprovalService
from app.config import Settings, clear_settings_cache
from app.exceptions import WorkflowTimeoutError
from app.models import Approval, WorkflowExecution
from app.models.enums import ApprovalStatus, WorkflowExecutionStatus, WorkflowName
from app.orchestration.handlers import build_default_handlers
from app.orchestration.schemas import WorkflowTriggerRequest
from app.orchestration.service import N8nOrchestrationService


SECRET = "test-n8n-secret"


def _n8n_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        n8n_webhook_secret=SecretStr(SECRET),
        n8n_default_timeout_seconds=30.0,
        n8n_max_execution_retries=2,
        n8n_webhook_require_timestamp=False,
        n8n_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
        health_rate_limit_per_minute=10_000,
    )
    base.update(overrides)
    return Settings(**base)


def _headers(secret: str = SECRET) -> dict[str, str]:
    return {"X-N8N-Webhook-Secret": secret, "Content-Type": "application/json"}


def _ok_handlers() -> dict:
    return {
        WorkflowName.DAILY_CYCLE.value: lambda p, t: {"ok": True, "workflow": "daily_cycle"},
        WorkflowName.RESEARCH.value: lambda p, t: {"ok": True, "workflow": "research"},
        WorkflowName.AUDIT.value: lambda p, t: {"ok": True, "workflow": "audit"},
        WorkflowName.OUTREACH_APPROVAL_QUEUE.value: lambda p, t: {
            "pending_count": 0,
            "auto_approved": False,
            "approval_bypass_blocked": True,
        },
        WorkflowName.FOLLOW_UPS.value: lambda p, t: {
            "processed": 0,
            "sends_without_approval": 0,
        },
        WorkflowName.DAILY_REPORT.value: lambda p, t: {"ok": True, "workflow": "daily_report"},
        WorkflowName.ERROR_MONITORING.value: lambda p, t: {
            "failed_agent_runs": 0,
            "failed_workflow_executions": 0,
        },
    }


@pytest.fixture()
def n8n_app(settings):
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base  # noqa: F401 — register models on metadata
    from app.models.workflow_execution import WorkflowExecution  # noqa: F401

    clear_settings_cache()
    reset_db_state()
    cfg = _n8n_settings()
    application = create_app(cfg)
    application.state.n8n_handlers = _ok_handlers()
    yield application
    reset_db_state()
    clear_settings_cache()


@pytest.fixture()
def n8n_client(n8n_app):
    from fastapi.testclient import TestClient

    from app.database import get_engine
    from app.models import Base

    with TestClient(n8n_app) as client:
        # Lifespan init_db() builds a fresh :memory: engine; create schema on it.
        Base.metadata.create_all(bind=get_engine())
        yield client


WEBHOOKS = [
    "/api/v1/n8n/webhooks/daily-cycle",
    "/api/v1/n8n/webhooks/research",
    "/api/v1/n8n/webhooks/audit",
    "/api/v1/n8n/webhooks/outreach-approval-queue",
    "/api/v1/n8n/webhooks/follow-ups",
    "/api/v1/n8n/webhooks/daily-report",
    "/api/v1/n8n/webhooks/error-monitoring",
]


@pytest.mark.parametrize("path", WEBHOOKS)
def test_webhook_requires_auth(n8n_client, path):
    resp = n8n_client.post(path, json={"idempotency_key": "k1"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", WEBHOOKS)
def test_webhook_rejects_bad_secret(n8n_client, path):
    resp = n8n_client.post(
        path,
        json={"idempotency_key": "k1"},
        headers=_headers("wrong"),
    )
    assert resp.status_code == 401


@pytest.mark.parametrize("path", WEBHOOKS)
def test_webhook_succeeds_with_auth(n8n_client, path):
    resp = n8n_client.post(
        path,
        json={"idempotency_key": f"ok-{path}"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution"]["status"] == "succeeded"
    assert body["execution"]["idempotent_replay"] is False


def test_idempotent_replay(n8n_client):
    path = "/api/v1/n8n/webhooks/research"
    payload = {"idempotency_key": "research-dup-1", "payload": {"query": "x"}}
    first = n8n_client.post(path, json=payload, headers=_headers())
    second = n8n_client.post(path, json=payload, headers=_headers())
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["execution"]["id"] == second.json()["execution"]["id"]
    assert second.json()["execution"]["idempotent_replay"] is True


def test_failed_execution_retry_then_exhaust(n8n_app, n8n_client):
    calls = {"n": 0}

    def flaky(payload, timeout):
        calls["n"] += 1
        raise RuntimeError(f"boom-{calls['n']}")

    handlers = _ok_handlers()
    handlers[WorkflowName.RESEARCH.value] = flaky
    n8n_app.state.n8n_handlers = handlers

    path = "/api/v1/n8n/webhooks/research"
    key = {"idempotency_key": "research-retry-1"}
    r1 = n8n_client.post(path, json=key, headers=_headers())
    assert r1.status_code == 502
    assert r1.json()["execution"]["attempt"] == 1
    assert r1.json()["execution"]["retryable"] is True

    r2 = n8n_client.post(path, json=key, headers=_headers())
    assert r2.status_code == 502
    assert r2.json()["execution"]["attempt"] == 2
    assert r2.json()["execution"]["id"] == r1.json()["execution"]["id"]

    r3 = n8n_client.post(path, json=key, headers=_headers())
    assert r3.status_code == 502
    assert r3.json()["execution"]["attempt"] == 3

    r4 = n8n_client.post(path, json=key, headers=_headers())
    assert r4.status_code == 502
    assert r4.json()["execution"]["attempt"] == 3
    assert r4.json()["execution"]["idempotent_replay"] is True
    assert r4.json()["execution"]["retryable"] is False
    assert calls["n"] == 3


def test_timeout_status(n8n_app, n8n_client):
    def slow(payload, timeout):
        raise WorkflowTimeoutError("simulated timeout", details={"timeout_seconds": timeout})

    handlers = _ok_handlers()
    handlers[WorkflowName.AUDIT.value] = slow
    n8n_app.state.n8n_handlers = handlers

    resp = n8n_client.post(
        "/api/v1/n8n/webhooks/audit",
        json={"idempotency_key": "audit-timeout-1", "timeout_seconds": 10},
        headers=_headers(),
    )
    assert resp.status_code == 504
    assert resp.json()["execution"]["status"] == "timed_out"


def test_running_conflict(db_session):
    cfg = _n8n_settings()
    handlers = _ok_handlers()
    svc = N8nOrchestrationService(session=db_session, settings=cfg, handlers=handlers)
    # Seed a running execution
    row = WorkflowExecution(
        workflow_name=WorkflowName.DAILY_CYCLE,
        idempotency_key="running-1",
        status=WorkflowExecutionStatus.RUNNING,
        attempt=1,
        timeout_seconds=30,
    )
    db_session.add(row)
    db_session.commit()

    from app.exceptions import ConflictError

    with pytest.raises(ConflictError):
        svc.trigger(
            WorkflowName.DAILY_CYCLE,
            WorkflowTriggerRequest(idempotency_key="running-1"),
        )


def test_outreach_queue_never_approves(db_session):
    cfg = _n8n_settings()
    approvals = ApprovalService(db_session, cfg)
    created = approvals.request_approval(
        ApprovalRequest(
            action_type="sales.send_outreach",
            description="Send outreach to Acme",
            requested_by="sales_agent",
            action_payload={"outreach_id": "x"},
        )
    )
    db_session.commit()
    assert created.status == ApprovalStatus.PENDING

    resolver = MagicMock()
    # Use real default handler which must not call approve
    handlers = build_default_handlers(db_session, cfg)
    svc = N8nOrchestrationService(session=db_session, settings=cfg, handlers=handlers)
    view = svc.trigger(
        WorkflowName.OUTREACH_APPROVAL_QUEUE,
        WorkflowTriggerRequest(idempotency_key="queue-1", payload={"limit": 10}),
    )
    assert view.status == WorkflowExecutionStatus.SUCCEEDED
    assert view.result_summary["auto_approved"] is False
    assert view.result_summary["approval_bypass_blocked"] is True
    assert view.result_summary["pending_count"] >= 1

    row = db_session.get(Approval, created.id)
    assert row is not None
    assert row.status == ApprovalStatus.PENDING.value
    resolver.approve.assert_not_called()


def test_list_and_get_execution(n8n_client):
    create = n8n_client.post(
        "/api/v1/n8n/webhooks/follow-ups",
        json={"idempotency_key": "fu-list-1"},
        headers=_headers(),
    )
    eid = create.json()["execution"]["id"]
    got = n8n_client.get(f"/api/v1/n8n/executions/{eid}", headers=_headers())
    assert got.status_code == 200
    assert got.json()["id"] == eid

    listed = n8n_client.get(
        "/api/v1/n8n/executions",
        params={"workflow_name": "follow_ups"},
        headers=_headers(),
    )
    assert listed.status_code == 200
    assert any(item["id"] == eid for item in listed.json())


def test_bearer_auth_accepted(n8n_client):
    resp = n8n_client.post(
        "/api/v1/n8n/webhooks/error-monitoring",
        json={"idempotency_key": "err-bearer-1"},
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200


def test_n8n_workflow_files_are_thin():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "n8n" / "workflows"
    expected = {
        "daily-business-cycle.json",
        "research.json",
        "auditing.json",
        "outreach-approval-queue.json",
        "follow-ups.json",
        "daily-report.json",
        "error-monitoring.json",
    }
    files = {p.name for p in root.glob("*.json")}
    assert expected <= files
    for name in expected:
        data = __import__("json").loads((root / name).read_text(encoding="utf-8"))
        types = {n["type"] for n in data["nodes"]}
        assert types <= {
            "n8n-nodes-base.scheduleTrigger",
            "n8n-nodes-base.httpRequest",
        }
        assert data["meta"]["orchestration_only"] is True
        assert data["meta"]["approval_bypass"] is False
        assert data["meta"]["uncontrolled_loops"] is False
        # No self-referential loop nodes
        assert "n8n-nodes-base.splitInBatches" not in types
        http = next(n for n in data["nodes"] if n["type"] == "n8n-nodes-base.httpRequest")
        assert http.get("retryOnFail") is True
        assert http.get("maxTries", 0) <= 3
        header_names = {
            h["name"]
            for h in http["parameters"]["headerParameters"]["parameters"]
        }
        assert "X-N8N-Webhook-Secret" in header_names
        assert "X-N8N-Timestamp" in header_names


def test_execution_persisted(n8n_client, n8n_app):
    from app.database import get_session_factory

    n8n_client.post(
        "/api/v1/n8n/webhooks/daily-report",
        json={"idempotency_key": "persist-1"},
        headers=_headers(),
    )
    session = get_session_factory()()
    try:
        rows = session.scalars(select(WorkflowExecution)).all()
        assert any(r.idempotency_key == "persist-1" for r in rows)
    finally:
        session.close()
