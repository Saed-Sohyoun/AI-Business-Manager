"""Real-server owner E2E — full FastAPI stack, mocked providers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.agents.manager.schemas import ManagerRunResult
from app.models.company import Company
from app.models.enums import ApprovalStatus
from app.owner.session_auth import CSRF_HEADER, create_owner_account


OWNER_KEY = "wave4-e2e-owner-key"
EMAIL = "e2e-owner@example.com"
PASSWORD = "e2e-secure-password-99"


@pytest.fixture()
def e2e_settings(settings):
    return settings.model_copy(
        update={
            "owner_api_key": SecretStr(OWNER_KEY),
            "approval_authorized_resolvers": "owner,admin",
            "owner_login_rate_limit_per_minute": 200,
        }
    )


@pytest.fixture()
def e2e_client(e2e_settings):
    from fastapi.testclient import TestClient

    from app.config import clear_settings_cache
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clear_settings_cache()
    reset_db_state()
    app = create_app(e2e_settings)
    engine = init_db(e2e_settings)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as client:
        yield client
    reset_db_state()
    clear_settings_cache()


def _headers() -> dict[str, str]:
    return {"X-Owner-API-Key": OWNER_KEY, "X-Owner-Resolver": "owner"}


def test_flow1_login_find_opportunities_appear(e2e_client):
    from app.database import get_session_factory

    session = get_session_factory()()
    try:
        create_owner_account(session, email=EMAIL, password=PASSWORD)
    finally:
        session.close()

    login = e2e_client.post(
        "/api/v1/owner/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    assert login.status_code == 200
    csrf = login.json()["data"]["csrf_token"]

    overview = e2e_client.get("/api/v1/owner/dashboard/summary")
    assert overview.status_code == 200

    fake_result = ManagerRunResult(
        manager_run_id=uuid4(),
        agent_run_id=uuid4(),
        status="succeeded",
        goal="find",
        phase="done",
        plan_summary="Found sample companies",
    )

    with patch("app.owner.commands.ManagerAgent") as MockManager:
        MockManager.return_value.run.return_value = fake_result
        with patch("app.owner.commands.build_manager_executor", return_value=MagicMock()):
            # Persist company as if research completed synchronously after spawn
            def _spawn(execution_id, **kwargs):
                from app.database import get_session_factory
                from app.models.owner_execution import OwnerExecution
                from app.models.owner_execution_enums import OwnerExecutionState
                from app.models.base import utc_now

                s = get_session_factory()()
                try:
                    s.add(
                        Company(
                            name="E2E Clean Co",
                            website="https://e2e-clean.example",
                            website_domain="e2e-clean.example",
                        )
                    )
                    row = s.get(OwnerExecution, execution_id)
                    if row:
                        row.status = OwnerExecutionState.COMPLETED.value
                        row.current_activity = "Completed"
                        row.progress = 100
                        row.completed_at = utc_now()
                        row.result_summary = "Found opportunities"
                    s.commit()
                finally:
                    s.close()

            with patch(
                "app.owner.commands.OwnerCommandService._spawn_find_opportunities",
                side_effect=_spawn,
            ):
                accepted = e2e_client.post(
                    "/api/v1/owner/commands/find-opportunities",
                    headers={CSRF_HEADER: csrf},
                    json={
                        "niche": "cleaning",
                        "location": "Berlin",
                        "desired_count": 2,
                        "idempotency_key": "e2e-flow1-idem-key01",
                    },
                )
    assert accepted.status_code == 202
    eid = accepted.json()["data"]["execution_id"]
    progress = e2e_client.get(f"/api/v1/owner/executions/{eid}")
    assert progress.status_code == 200
    assert progress.json()["data"]["state"] == "completed"

    opps = e2e_client.get("/api/v1/owner/opportunities")
    assert opps.status_code == 200
    assert opps.json()["data"]["total"] >= 1


def test_flow2_approval_persists(e2e_client):
    from app.approvals.schemas import ApprovalRequest
    from app.approvals.service import ApprovalService
    from app.database import get_session_factory

    session = get_session_factory()()
    try:
        settings = e2e_client.app.state.settings
        svc = ApprovalService(session, settings)
        view = svc.request_approval(
            ApprovalRequest(
                action_type="sales.send_outreach",
                description="Email Acme about opportunity",
                requested_by="sales",
                action_payload={
                    "recipient_email": "a@example.com",
                    "subject": "Hi",
                    "body_text": "Hello",
                },
            )
        )
        session.commit()
        approval_id = view.id
    finally:
        session.close()

    pending = e2e_client.get(
        "/api/v1/owner/approvals?status=pending", headers=_headers()
    )
    assert pending.status_code == 200
    assert any(str(a["id"]) == str(approval_id) for a in pending.json()["data"])

    approved = e2e_client.post(
        f"/api/v1/owner/approvals/{approval_id}/approve",
        headers=_headers(),
        json={"note": "ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == ApprovalStatus.APPROVED.value


def test_flow3_pause_outbound_blocks(e2e_client):
    from app.owner.controls import SystemControlService
    from app.database import get_session_factory
    from app.exceptions import ForbiddenError

    pause = e2e_client.post(
        "/api/v1/owner/system/pause-outbound",
        headers=_headers(),
        json={"reason": "e2e"},
    )
    assert pause.status_code == 200
    assert pause.json()["data"]["outbound_enabled"] is False

    session = get_session_factory()()
    try:
        with pytest.raises(ForbiddenError):
            SystemControlService(session).assert_outbound(actor="sales")
    finally:
        session.close()

    status = e2e_client.get("/api/v1/owner/system/status", headers=_headers())
    assert status.json()["data"]["outbound"] is False


def test_flow4_safe_mode_and_clear(e2e_client):
    enter = e2e_client.post(
        "/api/v1/owner/system/enter-safe-mode",
        headers=_headers(),
        json={"reason": "e2e safe"},
    )
    assert enter.status_code == 200
    assert enter.json()["data"]["system_mode"] == "safe_mode"

    # High-risk resume outbound denied while safe
    resume = e2e_client.post(
        "/api/v1/owner/system/resume-outbound",
        headers=_headers(),
        json={"reason": "try"},
    )
    assert resume.status_code == 403

    clear = e2e_client.post(
        "/api/v1/owner/system/clear-safe-mode",
        headers=_headers(),
        json={"reason": "cleared"},
    )
    assert clear.status_code == 200
    assert clear.json()["data"]["system_mode"] != "safe_mode"
