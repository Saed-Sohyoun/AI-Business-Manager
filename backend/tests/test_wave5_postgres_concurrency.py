"""Wave 5 — Postgres concurrency suite (REQUIRED for pilot readiness).

Set POSTGRES_TEST_URL to a disposable Postgres database, e.g.:
  postgresql+psycopg://postgres:postgres@localhost:5432/ai_bos_wave5_test

These tests FAIL CLOSED (skip = not a pass). Wave 5 readiness treats skip as BLOCKED.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_URL required — Wave 5 Postgres concurrency is BLOCKED when unset",
)


@pytest.fixture()
def pg_settings(settings):
    return settings.model_copy(
        update={
            "database_url": POSTGRES_URL,
            "owner_api_key": SecretStr("pg-owner-key-wave5"),
            "approval_authorized_resolvers": "owner,admin",
            "n8n_webhook_secret": SecretStr("pg-n8n-secret-wave5"),
            "n8n_webhook_require_signature": True,
            "n8n_webhook_require_timestamp": True,
        }
    )


@pytest.fixture()
def pg_app(pg_settings):
    from app.config import clear_settings_cache
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clear_settings_cache()
    reset_db_state()
    application = create_app(pg_settings)
    engine = init_db(pg_settings, force=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield application
    reset_db_state()
    clear_settings_cache()


@pytest.fixture()
def pg_client(pg_app):
    from fastapi.testclient import TestClient

    with TestClient(pg_app) as client:
        yield client


def _headers() -> dict[str, str]:
    return {"X-Owner-API-Key": "pg-owner-key-wave5", "X-Owner-Resolver": "owner"}


def test_idempotent_command_under_concurrency(pg_client):
    body = {
        "niche": "cafes",
        "location": "Berlin",
        "desired_count": 1,
        "idempotency_key": "pg-idem-concurrent-001",
    }
    with patch("app.owner.commands.OwnerCommandService._spawn_find_opportunities"):

        def once():
            return pg_client.post(
                "/api/v1/owner/commands/find-opportunities",
                headers=_headers(),
                json=body,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(once) for _ in range(8)]
            results = [f.result() for f in as_completed(futures)]
    assert all(r.status_code == 202 for r in results)
    ids = {r.json()["data"]["execution_id"] for r in results}
    assert len(ids) == 1


def test_simultaneous_approve_approve_race(pg_client, pg_settings):
    from app.approvals.schemas import ApprovalRequest
    from app.approvals.service import ApprovalService
    from app.database import get_session_factory
    from app.models.enums import ApprovalStatus

    session = get_session_factory()()
    try:
        view = ApprovalService(session, pg_settings).request_approval(
            ApprovalRequest(
                action_type="sales.send_outreach",
                description="Race approve/approve",
                requested_by="sales",
                action_payload={
                    "recipient_email": "race@example.com",
                    "subject": "Hi",
                    "body_text": "Hello",
                },
            )
        )
        session.commit()
        approval_id = view.id
    finally:
        session.close()

    def approve():
        return pg_client.post(
            f"/api/v1/owner/approvals/{approval_id}/approve",
            headers=_headers(),
            json={"note": "ok"},
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [f.result() for f in as_completed([pool.submit(approve) for _ in range(6)])]
    oks = [r for r in results if r.status_code == 200]
    conflicts = [r for r in results if r.status_code in {409, 422}]
    assert len(oks) == 1
    assert len(oks) + len(conflicts) == len(results)
    assert oks[0].json()["data"]["status"] == ApprovalStatus.APPROVED.value


def test_approve_reject_race(pg_client, pg_settings):
    from app.approvals.schemas import ApprovalRequest
    from app.approvals.service import ApprovalService
    from app.database import get_session_factory
    from app.models.enums import ApprovalStatus

    session = get_session_factory()()
    try:
        view = ApprovalService(session, pg_settings).request_approval(
            ApprovalRequest(
                action_type="sales.send_outreach",
                description="Race approve/reject",
                requested_by="sales",
                action_payload={
                    "recipient_email": "race2@example.com",
                    "subject": "Hi",
                    "body_text": "Hello",
                },
            )
        )
        session.commit()
        approval_id = view.id
    finally:
        session.close()

    def approve():
        return pg_client.post(
            f"/api/v1/owner/approvals/{approval_id}/approve",
            headers=_headers(),
            json={"note": "yes"},
        )

    def reject():
        return pg_client.post(
            f"/api/v1/owner/approvals/{approval_id}/reject",
            headers=_headers(),
            json={"note": "no"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(approve)
        f2 = pool.submit(reject)
        r1, r2 = f1.result(), f2.result()
    winners = [r for r in (r1, r2) if r.status_code == 200]
    losers = [r for r in (r1, r2) if r.status_code in {409, 422}]
    assert len(winners) == 1
    assert len(losers) == 1
    status = winners[0].json()["data"]["status"]
    assert status in {ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value}


def test_execution_transition_race(pg_client):
    from app.database import get_session_factory
    from app.models.owner_execution import OwnerExecution
    from app.models.owner_execution_enums import OwnerCommandType, OwnerExecutionState
    from app.models.base import utc_now

    session = get_session_factory()()
    try:
        row = OwnerExecution(
            command_type=OwnerCommandType.FIND_OPPORTUNITIES.value,
            title="Race exec",
            purpose="concurrency",
            status=OwnerExecutionState.QUEUED.value,
            idempotency_key=f"exec-race-{uuid4().hex[:12]}",
            requested_by="owner",
            started_at=utc_now(),
            request_payload={},
        )
        session.add(row)
        session.commit()
        eid = row.id
    finally:
        session.close()

    def cancel():
        return pg_client.post(
            f"/api/v1/owner/executions/{eid}/cancel",
            headers=_headers(),
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [f.result() for f in as_completed([pool.submit(cancel) for _ in range(6)])]
    assert all(r.status_code == 200 for r in results)
    states = {r.json()["data"]["state"] for r in results}
    assert states == {"cancelled"}


def test_webhook_nonce_race(pg_settings):
    import time
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from app.config import clear_settings_cache
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base
    from app.orchestration.auth import sign_n8n_request

    clear_settings_cache()
    reset_db_state()
    app = create_app(pg_settings)
    engine = init_db(pg_settings, force=True)
    Base.metadata.create_all(bind=engine)

    path = "/api/v1/n8n/webhooks/research"
    body = b'{"idempotency_key":"nonce-race-1","payload":{},"timeout_seconds":5}'
    ts = str(int(time.time()))
    nonce = uuid4().hex
    secret = "pg-n8n-secret-wave5"
    sig = sign_n8n_request(
        secret=secret, timestamp=ts, method="POST", path=path, body=body
    )
    headers = {
        "X-N8N-Webhook-Secret": secret,
        "X-N8N-Timestamp": ts,
        "X-N8N-Nonce": nonce,
        "X-N8N-Signature": sig,
        "Content-Type": "application/json",
    }

    mock_handlers = MagicMock()
    mock_handlers.research = MagicMock(return_value={"ok": True})
    app.state.n8n_handlers = mock_handlers

    with TestClient(app) as client:

        def once():
            return client.post(path, content=body, headers=headers)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = [f.result() for f in as_completed([pool.submit(once) for _ in range(8)])]
    ok = [r for r in results if r.status_code < 400]
    rejected = [r for r in results if r.status_code in {401, 403, 409}]
    assert len(ok) == 1, {r.status_code for r in results}
    assert len(rejected) >= 1
    reset_db_state()
    clear_settings_cache()


def test_system_control_singleton_race(pg_settings):
    from app.database import get_session_factory, init_db, reset_db_state
    from app.config import clear_settings_cache
    from app.models import Base
    from app.models.system_control import SYSTEM_CONTROL_KEY, SystemControlState
    from app.owner.controls import SystemControlService
    from sqlalchemy import func, select

    clear_settings_cache()
    reset_db_state()
    engine = init_db(pg_settings, force=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def create_once():
        session = get_session_factory()()
        try:
            SystemControlService(session).get_or_create()
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(as_completed([pool.submit(create_once) for _ in range(10)]))

    session = get_session_factory()()
    try:
        count = session.scalar(
            select(func.count())
            .select_from(SystemControlState)
            .where(SystemControlState.control_key == SYSTEM_CONTROL_KEY)
        )
        assert int(count or 0) == 1
    finally:
        session.close()
        reset_db_state()
        clear_settings_cache()


def test_duplicate_outbound_protection(pg_settings):
    """Concurrent identical outbound idempotency keys must not create duplicates."""
    from app.database import get_session_factory, init_db, reset_db_state
    from app.config import clear_settings_cache
    from app.models import Base, OutboundMessage
    from app.models.enums import OutboundMessageStatus
    from sqlalchemy import func, select
    from sqlalchemy.exc import IntegrityError

    clear_settings_cache()
    reset_db_state()
    engine = init_db(pg_settings, force=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    key = f"outbound-idem-{uuid4().hex[:12]}"

    def insert_once() -> str:
        session = get_session_factory()()
        try:
            row = OutboundMessage(
                idempotency_key=key,
                to_email="test@example.com",
                from_email="owner@example.com",
                subject="dup",
                body_text="hello",
                status=OutboundMessageStatus.QUEUED,
                provider="test",
            )
            session.add(row)
            session.commit()
            return "ok"
        except IntegrityError:
            session.rollback()
            return "dup"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = [f.result() for f in as_completed([pool.submit(insert_once) for _ in range(8)])]
    assert outcomes.count("ok") == 1
    assert outcomes.count("dup") == 7

    session = get_session_factory()()
    try:
        count = session.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(OutboundMessage.idempotency_key == key)
        )
        assert int(count or 0) == 1
    finally:
        session.close()
        reset_db_state()
        clear_settings_cache()
