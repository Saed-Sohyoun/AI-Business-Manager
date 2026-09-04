"""Wave 2 — Owner control plane tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from sqlalchemy import select

from app.approvals.schemas import ApprovalRequest
from app.approvals.service import ApprovalService
from app.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.models.base import utc_now
from app.models.enums import ApprovalStatus
from app.models.security_event import SecurityEvent
from app.owner.approvals import OwnerApprovalService
from app.owner.controls import SystemControlService
from app.owner.dashboard import DashboardService
from app.owner.permissions import has_owner_permission
from app.owner.safe_mode import SafeModeService, SafeModeThresholds
from app.owner.work import ActiveWorkService
from app.security.events import (
    AGENT_SCOPE_VIOLATION,
    OWNER_PAUSED_ALL,
    SAFE_MODE_CLEARED,
    SAFE_MODE_ENTERED,
    SYSTEM_CONTROL_DENIED,
)
from app.tools.gateway import ToolGateway


OWNER_KEY = "test-owner-secret-key-wave2"


@pytest.fixture()
def owner_settings(settings):
    return settings.model_copy(
        update={
            "owner_api_key": SecretStr(OWNER_KEY),
            "approval_authorized_resolvers": "owner,admin",
        }
    )


@pytest.fixture()
def owner_app(owner_settings):
    from app.config import clear_settings_cache
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clear_settings_cache()
    reset_db_state()
    application = create_app(owner_settings)
    engine = init_db(owner_settings)
    Base.metadata.create_all(bind=engine)
    yield application
    reset_db_state()
    clear_settings_cache()


@pytest.fixture()
def owner_client(owner_app):
    from fastapi.testclient import TestClient

    with TestClient(owner_app) as client:
        yield client


def _owner_headers(resolver: str = "owner") -> dict[str, str]:
    return {"X-Owner-API-Key": OWNER_KEY, "X-Owner-Resolver": resolver}


# --- Auth / authz -------------------------------------------------------------


def test_owner_auth_missing_key_401(owner_client):
    r = owner_client.get("/api/v1/owner/system/status")
    assert r.status_code == 401


def test_owner_auth_bad_key_401(owner_client):
    r = owner_client.get(
        "/api/v1/owner/system/status",
        headers={"X-Owner-API-Key": "wrong", "X-Owner-Resolver": "owner"},
    )
    assert r.status_code == 401
    assert "owner" not in r.text.lower() or "Invalid" in r.json()["error"]["message"]
    assert OWNER_KEY not in r.text


def test_owner_auth_unauthorized_resolver_403(owner_client):
    r = owner_client.get(
        "/api/v1/owner/system/status",
        headers={"X-Owner-API-Key": OWNER_KEY, "X-Owner-Resolver": "hacker"},
    )
    assert r.status_code == 403


def test_unknown_owner_permission_deny():
    assert has_owner_permission(frozenset({"owner.read_dashboard"}), "owner.hack") is False
    assert has_owner_permission(frozenset({"owner.read_dashboard"}), "owner.read_dashboard") is True


# --- Approvals API ------------------------------------------------------------


def _create_pending_approval(session, settings, *, description: str = "Send test email"):
    svc = ApprovalService(session, settings)
    view = svc.request_approval(
        ApprovalRequest(
            action_type="sales.send_outreach",
            description=description,
            requested_by="sales",
            action_payload={
                "recipient_email": "a@example.com",
                "subject": "Hi",
                "body_text": "Hello",
            },
        )
    )
    session.commit()
    return view


def test_approval_list_and_detail(owner_client, owner_settings, db_session):
    # Use same DB as app — recreate via owner app session
    from app.database import get_session_factory

    session = get_session_factory()()
    try:
        view = _create_pending_approval(session, owner_settings)
        r = owner_client.get("/api/v1/owner/approvals", headers=_owner_headers())
        assert r.status_code == 200
        items = r.json()["data"]
        assert any(i["id"] == str(view.id) for i in items)
        assert "fingerprint" not in items[0]  # primary UI uses advanced_details
        assert "title" in items[0]
        detail = owner_client.get(
            f"/api/v1/owner/approvals/{view.id}", headers=_owner_headers()
        )
        assert detail.status_code == 200
        body = detail.json()["data"]
        assert body["advanced_details"]["fingerprint"]
        assert body["status"] == "pending"
    finally:
        session.close()


def test_approve_and_reject(owner_client, owner_settings):
    from app.database import get_session_factory

    session = get_session_factory()()
    try:
        svc = ApprovalService(session, owner_settings)
        a = svc.request_approval(
            ApprovalRequest(
                action_type="sales.send_outreach",
                description="Approve me",
                requested_by="sales",
                action_payload={
                    "recipient_email": "a@example.com",
                    "subject": "Hi",
                    "body_text": "Hello",
                },
            )
        )
        b = svc.request_approval(
            ApprovalRequest(
                action_type="sales.send_outreach",
                description="Reject me",
                requested_by="sales",
                action_payload={
                    "recipient_email": "b@example.com",
                    "subject": "Hi2",
                    "body_text": "Hello2",
                },
            )
        )
        session.commit()

        ok = owner_client.post(
            f"/api/v1/owner/approvals/{a.id}/approve",
            headers=_owner_headers(),
            json={"note": "LGTM"},
        )
        assert ok.status_code == 200
        assert ok.json()["data"]["status"] == "approved"
        assert ok.json()["data"]["resolved_by"] == "owner"

        # idempotent second approve
        ok2 = owner_client.post(
            f"/api/v1/owner/approvals/{a.id}/approve",
            headers=_owner_headers(),
        )
        assert ok2.status_code == 200
        assert ok2.json()["data"]["status"] == "approved"

        rej = owner_client.post(
            f"/api/v1/owner/approvals/{b.id}/reject",
            headers=_owner_headers(),
            json={"note": "No"},
        )
        assert rej.status_code == 200
        assert rej.json()["data"]["status"] == "rejected"
    finally:
        session.close()


def test_approve_then_reject_is_conflict(owner_settings, db_session):
    view = _create_pending_approval(db_session, owner_settings)
    OwnerApprovalService(db_session, owner_settings).approve(view.id, owner_id="owner")
    with pytest.raises(ConflictError):
        OwnerApprovalService(db_session, owner_settings).reject(view.id, owner_id="owner")


def test_double_approve_is_idempotent(owner_settings, db_session):
    view = _create_pending_approval(db_session, owner_settings)
    first = OwnerApprovalService(db_session, owner_settings).approve(view.id, owner_id="owner")
    second = OwnerApprovalService(db_session, owner_settings).approve(view.id, owner_id="owner")
    assert first.status == "approved"
    assert second.status == "approved"


def test_cannot_approve_expired(owner_client, owner_settings):
    from app.database import get_session_factory
    from app.models import Approval

    session = get_session_factory()()
    try:
        view = _create_pending_approval(session, owner_settings)
        row = session.get(Approval, view.id)
        row.expires_at = utc_now() - timedelta(hours=1)
        session.commit()
        r = owner_client.post(
            f"/api/v1/owner/approvals/{view.id}/approve",
            headers=_owner_headers(),
        )
        assert r.status_code == 422
    finally:
        session.close()


def test_cannot_approve_rejected(owner_client, owner_settings):
    from app.database import get_session_factory

    session = get_session_factory()()
    try:
        view = _create_pending_approval(session, owner_settings)
        OwnerApprovalService(session, owner_settings).reject(
            view.id, owner_id="owner", note="no"
        )
        r = owner_client.post(
            f"/api/v1/owner/approvals/{view.id}/approve",
            headers=_owner_headers(),
        )
        assert r.status_code == 409
    finally:
        session.close()


# --- System controls ----------------------------------------------------------


def test_pause_all_and_status(owner_client):
    r = owner_client.post(
        "/api/v1/owner/system/pause-all",
        headers=_owner_headers(),
        json={"reason": "emergency"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["system_mode"] == "paused_by_owner"
    assert data["ai_operations_enabled"] is False
    assert data["outbound_enabled"] is False
    assert data["spending_enabled"] is False
    assert data["browser_automation_enabled"] is False

    st = owner_client.get("/api/v1/owner/system/status", headers=_owner_headers())
    assert st.status_code == 200
    body = st.json()["data"]
    assert body["system_mode"] == "paused_by_owner"
    assert body["ai_operations"] is False
    assert "owner_api_key" not in st.text.lower()
    assert OWNER_KEY not in st.text


def test_pause_resume_outbound_spending_browser(owner_client):
    for path in (
        "/api/v1/owner/system/pause-outbound",
        "/api/v1/owner/system/pause-spending",
        "/api/v1/owner/system/pause-browser",
        "/api/v1/owner/system/pause-ai",
    ):
        r = owner_client.post(path, headers=_owner_headers(), json={"reason": "test"})
        assert r.status_code == 200, path

    for path in (
        "/api/v1/owner/system/resume-ai",
        "/api/v1/owner/system/resume-outbound",
        "/api/v1/owner/system/resume-spending",
        "/api/v1/owner/system/resume-browser",
    ):
        r = owner_client.post(path, headers=_owner_headers(), json={"reason": "test"})
        assert r.status_code == 200, path


def test_safe_mode_enter_clear(owner_client):
    r = owner_client.post(
        "/api/v1/owner/system/enter-safe-mode",
        headers=_owner_headers(),
        json={"reason": "threshold test"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["system_mode"] == "safe_mode"
    assert r.json()["data"]["outbound_enabled"] is False

    # Resume outbound blocked while safe mode
    blocked = owner_client.post(
        "/api/v1/owner/system/resume-outbound",
        headers=_owner_headers(),
    )
    assert blocked.status_code == 403

    cleared = owner_client.post(
        "/api/v1/owner/system/clear-safe-mode",
        headers=_owner_headers(),
        json={"reason": "cleared"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["system_mode"] == "normal"


def test_agent_cannot_clear_safe_mode(db_session, owner_settings):
    controls = SystemControlService(db_session)
    controls.enter_safe_mode(reason="test", actor="system:safe_mode")
    with pytest.raises(ForbiddenError):
        controls.clear_safe_mode(actor="manager")
    with pytest.raises(ForbiddenError):
        controls.clear_safe_mode(actor="research")
    with pytest.raises(ForbiddenError):
        controls.set_control("outbound", enabled=True, actor="sales")
    with pytest.raises(ForbiddenError):
        controls.set_control("spending", enabled=True, actor="finance")


def test_agent_cannot_use_owner_tools_via_gateway(db_session):
    gw = ToolGateway("manager", session=db_session)
    with pytest.raises(ForbiddenError):
        gw.require_action("owner.resume_outbound")
    with pytest.raises(Exception):
        gw.require("resume_outbound")
    unknown = ToolGateway("research", session=db_session)
    with pytest.raises(ForbiddenError):
        unknown.require_action("owner.clear_safe_mode")


# --- Enforcement --------------------------------------------------------------


def test_ai_disabled_blocks_research(db_session, owner_settings):
    from app.agents.research.agent import ResearchAgent
    from app.agents.research.schemas import ResearchRequest
    from app.services.search_service import SearchService

    SystemControlService(db_session).set_control(
        "ai_operations", enabled=False, actor="owner"
    )
    agent = ResearchAgent(
        session=db_session,
        search_service=MagicMock(spec=SearchService),
        browser_service=None,
        settings=owner_settings,
    )
    result = agent.run(ResearchRequest(query="dentists berlin"))
    assert result.status == "failed"
    assert "disabled" in (result.error_message or "").lower() or result.logs


def test_ai_disabled_blocks_audit(db_session, owner_settings):
    from app.agents.audit.agent import AuditAgent
    from app.agents.audit.schemas import AuditRequest

    SystemControlService(db_session).set_control(
        "ai_operations", enabled=False, actor="owner"
    )
    agent = AuditAgent(
        session=db_session,
        browser_service=None,
        search_service=None,
        ai_service=None,
        settings=owner_settings,
    )
    result = agent.run(AuditRequest(company_ids=[], max_audits=1))
    assert result.status == "failed"


def test_ai_disabled_blocks_manager(db_session, owner_settings):
    from app.agents.manager.agent import ManagerAgent
    from app.agents.manager.schemas import ManagerRequest

    SystemControlService(db_session).set_control(
        "ai_operations", enabled=False, actor="owner"
    )
    agent = ManagerAgent(
        session=db_session,
        executor=MagicMock(),
        settings=owner_settings,
    )
    result = agent.run(ManagerRequest(goal="Grow pipeline"))
    assert result.status == "failed"


def test_outbound_disabled_blocks_email_even_if_approved(db_session, owner_settings):
    from app.services.email_service import EmailService

    SystemControlService(db_session).set_control(
        "outbound", enabled=False, actor="owner"
    )
    svc = EmailService(MagicMock(), session=db_session, settings=owner_settings)
    with pytest.raises(ForbiddenError):
        svc.send(
            to_email="a@example.com",
            subject="Hi",
            body_text="Hello",
            idempotency_key=f"k-{uuid4()}",
            approval_id=uuid4(),
        )


def test_spending_disabled_blocks_cost(db_session, owner_settings):
    from app.agents.finance.agent import FinanceAgent
    from app.agents.finance.schemas import CostRecordRequest
    from app.models.enums import CostCategory

    SystemControlService(db_session).set_control(
        "spending", enabled=False, actor="owner"
    )
    agent = FinanceAgent(session=db_session, settings=owner_settings)
    with pytest.raises(ForbiddenError):
        agent.record_cost(
            CostRecordRequest(
                amount=Decimal("1.00"),
                currency="EUR",
                category=CostCategory.OTHER_OPERATIONAL,
                source="test",
                description="blocked",
                idempotency_key=f"cost-{uuid4()}",
            )
        )


def test_browser_disabled_blocks_fetch(db_session, owner_settings):
    from app.services.browser_service import BrowserService

    SystemControlService(db_session).set_control(
        "browser_automation", enabled=False, actor="owner"
    )
    provider = MagicMock()
    svc = BrowserService(provider, session=db_session)
    with pytest.raises(ForbiddenError):
        svc.fetch_page("https://example.com")
    provider.fetch.assert_not_called()


def test_safe_mode_blocks_outbound_and_spending(db_session, owner_settings):
    controls = SystemControlService(db_session)
    controls.enter_safe_mode(reason="attacks", actor="system:safe_mode")
    with pytest.raises(ForbiddenError):
        controls.assert_outbound(actor="email_service")
    with pytest.raises(ForbiddenError):
        controls.assert_spending(actor="finance")


def test_safe_mode_service_threshold(db_session):
    from app.security.events import record_security_event

    for _ in range(5):
        record_security_event(
            db_session, event_type=AGENT_SCOPE_VIOLATION, agent_id="research", reason="x"
        )
    db_session.commit()
    svc = SafeModeService(
        db_session, thresholds=SafeModeThresholds(scope_violations=5, policy_denials=99)
    )
    assert svc.evaluate_and_maybe_enter() is True
    state = SystemControlService(db_session).get_or_create()
    assert state.system_mode == "safe_mode"


# --- Dashboard / work / alerts / security -------------------------------------


def test_dashboard_summary_zeros(owner_client):
    r = owner_client.get("/api/v1/owner/dashboard/summary", headers=_owner_headers())
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["money"]["revenue"] == "0.00" or data["money"]["revenue"].startswith("0")
    assert data["pipeline"]["companies"] == 0
    assert data["attention"]["pending_approvals"] == 0
    assert isinstance(data["recent_activity"], list)


def test_active_work_empty(owner_client):
    r = owner_client.get("/api/v1/owner/work/active", headers=_owner_headers())
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []


def test_alerts_and_security_events(owner_client):
    owner_client.post(
        "/api/v1/owner/system/pause-all",
        headers=_owner_headers(),
        json={"reason": "alert test"},
    )
    alerts = owner_client.get("/api/v1/owner/alerts", headers=_owner_headers())
    assert alerts.status_code == 200
    assert len(alerts.json()["data"]["items"]) >= 1

    events = owner_client.get("/api/v1/owner/security-events", headers=_owner_headers())
    assert events.status_code == 200
    types = [e["advanced_details"]["event_type"] for e in events.json()["data"]["items"]]
    assert OWNER_PAUSED_ALL in types
    blob = events.text.lower()
    assert "secret" not in blob or "api_key" not in blob
    assert OWNER_KEY not in events.text


def test_pause_all_security_event_persisted(db_session):
    SystemControlService(db_session).pause_all(actor="owner", reason="kill")
    rows = list(
        db_session.scalars(
            select(SecurityEvent).where(SecurityEvent.event_type == OWNER_PAUSED_ALL)
        ).all()
    )
    assert len(rows) >= 1
