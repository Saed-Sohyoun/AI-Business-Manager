"""Human approval system tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.manager import ManagerAgent, ManagerRequest, PlannedTaskSpec, RegistryExecutor
from app.agents.manager.schemas import DelegationResult
from app.approvals import (
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalResolver,
    ApprovalService,
    ResolveApprovalRequest,
)
from app.config import Settings
from app.exceptions import ConflictError, ForbiddenError, ValidationAppError
from app.models import Approval, ApprovalEvent, ManagerTask
from app.models.enums import ApprovalStatus, ManagerTaskStatus, RiskLevel


@pytest.fixture()
def approval_settings(settings) -> Settings:
    return Settings(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        approval_default_ttl_seconds=3600,
        approval_authorized_resolvers="owner,admin",
        approval_required_for_external_actions=True,
        max_agent_runtime_seconds=60,
        max_retries=2,
        max_tasks_per_run=10,
        max_ai_cost_per_run=Decimal("5.00"),
    )


@pytest.fixture()
def approval_svc(db_session, approval_settings):
    return ApprovalService(db_session, approval_settings)


@pytest.fixture()
def resolver(db_session, approval_settings, approval_svc):
    return ApprovalResolver(db_session, approval_settings, service=approval_svc)


def test_policy_levels():
    policy = ApprovalPolicy()
    assert policy.classify("research.discover_companies") == RiskLevel.GREEN
    assert policy.classify("scoring.score_companies") == RiskLevel.GREEN
    assert policy.classify("audit.audit_digital_presence") == RiskLevel.GREEN
    assert policy.classify("database.update") == RiskLevel.GREEN
    assert policy.classify("analysis.internal") == RiskLevel.GREEN
    assert policy.classify("report.generate") == RiskLevel.GREEN
    assert policy.classify("sales.draft_outreach") == RiskLevel.GREEN
    assert policy.classify("sales.first_outreach") == RiskLevel.YELLOW
    assert policy.classify("commerce.discount") == RiskLevel.YELLOW
    assert policy.classify("commerce.purchase") == RiskLevel.YELLOW
    assert policy.classify("tools.paid") == RiskLevel.YELLOW
    assert policy.classify("strategy.major_change") == RiskLevel.YELLOW
    assert policy.classify("finance.money_transfer") == RiskLevel.RED
    assert policy.classify("legal.contract") == RiskLevel.RED
    assert policy.classify("legal.commitment") == RiskLevel.RED
    assert policy.classify("action.irreversible_high_impact") == RiskLevel.RED
    assert policy.classify("totally.unknown.action") == RiskLevel.RED


def test_automatic_green_action(approval_svc):
    gate = approval_svc.evaluate_gate("research.discover_companies")
    assert gate.decision == "allow_auto"
    assert gate.may_execute is True
    assert approval_svc.assert_executable("research.discover_companies").may_execute is True


def test_approval_required_yellow_action(approval_svc, db_session):
    gate = approval_svc.evaluate_gate("sales.first_outreach")
    assert gate.decision == "require_approval"
    assert gate.may_execute is False

    view = approval_svc.request_approval(
        ApprovalRequest(
            action_type="sales.first_outreach",
            description="First email to Acme",
            requested_by="manager",
            action_payload={"lead_id": "abc"},
        )
    )
    db_session.commit()
    assert view.status == ApprovalStatus.PENDING
    assert view.risk_level == RiskLevel.YELLOW
    assert view.expires_at is not None
    events = approval_svc.list_events(view.id)
    assert any(e.event_type == "requested" for e in events)

    still = approval_svc.evaluate_gate("sales.first_outreach", approval_id=view.id)
    assert still.may_execute is False


def test_approved_action_then_executable(approval_svc, resolver, db_session):
    view = approval_svc.request_approval(
        ApprovalRequest(
            action_type="sales.first_outreach",
            description="First outreach",
            requested_by="manager",
            action_payload={"to": "a@example.com"},
        )
    )
    db_session.commit()
    approved = resolver.approve(
        ResolveApprovalRequest(approval_id=view.id, resolved_by="owner", note="OK to send")
    )
    assert approved.status == ApprovalStatus.APPROVED
    gate = approval_svc.evaluate_gate("sales.first_outreach", approval_id=view.id)
    assert gate.may_execute is True
    approval_svc.assert_executable("sales.first_outreach", approval_id=view.id)

    # Immutable after resolution
    with pytest.raises(ConflictError):
        resolver.approve(ResolveApprovalRequest(approval_id=view.id, resolved_by="owner"))


def test_rejected_action_not_executable(approval_svc, resolver, db_session):
    view = approval_svc.request_approval(
        ApprovalRequest(
            action_type="commerce.discount",
            description="20% discount",
            requested_by="manager",
            action_payload={"pct": 20},
        )
    )
    db_session.commit()
    rejected = resolver.reject(
        ResolveApprovalRequest(approval_id=view.id, resolved_by="admin", note="Too high")
    )
    assert rejected.status == ApprovalStatus.REJECTED
    gate = approval_svc.evaluate_gate("commerce.discount", approval_id=view.id)
    assert gate.decision == "deny"
    assert gate.may_execute is False
    with pytest.raises(ForbiddenError):
        approval_svc.assert_executable("commerce.discount", approval_id=view.id)


def test_expired_approval(approval_settings, db_session):
    clock = {"now": datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)}

    def now() -> datetime:
        return clock["now"]

    svc = ApprovalService(db_session, approval_settings, clock=now)
    resolver = ApprovalResolver(db_session, approval_settings, service=svc)
    view = svc.request_approval(
        ApprovalRequest(
            action_type="tools.paid",
            description="Buy SaaS seat",
            requested_by="manager",
            action_payload={"sku": "pro"},
            expires_in_seconds=60,
        )
    )
    db_session.commit()
    clock["now"] = clock["now"] + timedelta(seconds=120)
    expired = svc.expire_if_due(db_session.get(Approval, view.id))
    assert expired is True
    db_session.commit()
    refreshed = svc.get_approval(view.id)
    assert refreshed.status == ApprovalStatus.EXPIRED
    with pytest.raises(ValidationAppError):
        resolver.approve(ResolveApprovalRequest(approval_id=view.id, resolved_by="owner"))
    with pytest.raises(ForbiddenError):
        svc.assert_executable("tools.paid", approval_id=view.id)


def test_duplicate_approval(approval_svc, db_session):
    req = ApprovalRequest(
        action_type="strategy.major_change",
        description="Pivot GTM",
        requested_by="manager",
        action_payload={"plan": "b"},
        fingerprint="dup-fingerprint-001",
    )
    first = approval_svc.request_approval(req)
    db_session.commit()
    with pytest.raises(ConflictError) as exc:
        approval_svc.request_approval(req)
    assert exc.value.details["approval_id"] == str(first.id)
    events = approval_svc.list_events(first.id)
    assert any(e.event_type == "duplicate_request" for e in events)


def test_unauthorized_approval(approval_svc, resolver, db_session):
    view = approval_svc.request_approval(
        ApprovalRequest(
            action_type="sales.first_outreach",
            description="Outreach",
            requested_by="manager",
            action_payload={"x": 1},
        )
    )
    db_session.commit()
    with pytest.raises(ForbiddenError):
        resolver.approve(ResolveApprovalRequest(approval_id=view.id, resolved_by="manager"))
    with pytest.raises(ForbiddenError):
        resolver.approve(ResolveApprovalRequest(approval_id=view.id, resolved_by="hacker"))
    with pytest.raises(ForbiddenError):
        resolver.reject(ResolveApprovalRequest(approval_id=view.id, resolved_by="system"))


def test_attempted_bypass(approval_svc, db_session):
    # Cannot execute YELLOW without approval
    with pytest.raises(ForbiddenError):
        approval_svc.assert_executable("sales.first_outreach")

    # Cannot under-classify risk to GREEN
    with pytest.raises(ForbiddenError):
        approval_svc.request_approval(
            ApprovalRequest(
                action_type="finance.money_transfer",
                description="try bypass",
                requested_by="manager",
                risk_level=RiskLevel.GREEN,
                action_payload={"amount": 1},
            )
        )

    # RED never agent-executable even if someone forges an approved row
    forged = Approval(
        action_type="finance.money_transfer",
        description="forged",
        risk_level=RiskLevel.RED,
        status=ApprovalStatus.APPROVED,
        fingerprint=f"forged-{uuid4().hex[:16]}",
        requested_by="attacker",
        action_payload={"amount": 999},
    )
    db_session.add(forged)
    db_session.commit()
    gate = approval_svc.evaluate_gate("finance.money_transfer", approval_id=forged.id)
    assert gate.decision == "human_only"
    assert gate.may_execute is False
    with pytest.raises(ForbiddenError):
        approval_svc.assert_executable("finance.money_transfer", approval_id=forged.id)

    # Approval for wrong action_type cannot unlock a different YELLOW action
    yellow = approval_svc.request_approval(
        ApprovalRequest(
            action_type="sales.first_outreach",
            description="ok",
            requested_by="manager",
            action_payload={"a": 1},
        )
    )
    db_session.commit()
    yellow_row = db_session.get(Approval, yellow.id)
    yellow_row.status = ApprovalStatus.APPROVED
    db_session.commit()
    mismatched = approval_svc.evaluate_gate("commerce.discount", approval_id=yellow.id)
    assert mismatched.decision == "deny"
    assert mismatched.may_execute is False


def test_manager_respects_green_auto(db_session, approval_settings):
    def ok_research(payload: dict, timeout: float) -> DelegationResult:
        return DelegationResult(
            status="succeeded",
            summary="ok",
            output={"companies_created": 1},
        )

    registry = RegistryExecutor()
    registry.register("research", "discover_companies", ok_research)
    agent = ManagerAgent(session=db_session, executor=registry, settings=approval_settings)
    result = agent.run(
        ManagerRequest(
            goal="Research only",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="research",
                    task_type="discover_companies",
                    payload={"query": "cafes", "max_companies": 1},
                    rationale="green",
                )
            ],
        )
    )
    assert result.status == "succeeded"
    assert result.tasks_succeeded == 1


def test_manager_approved_yellow_then_executes(db_session, approval_settings):
    calls = {"n": 0}

    def outreach(payload: dict, timeout: float) -> DelegationResult:
        calls["n"] += 1
        return DelegationResult(
            status="succeeded",
            summary="draft queued",
            output={"queued": True},
        )

    registry = RegistryExecutor()
    registry.register("sales", "first_outreach", outreach)
    svc = ApprovalService(db_session, approval_settings)
    resolver = ApprovalResolver(db_session, approval_settings, service=svc)
    agent = ManagerAgent(
        session=db_session,
        executor=registry,
        settings=approval_settings,
        approval_service=svc,
    )

    first = agent.run(
        ManagerRequest(
            goal="Outreach",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="sales",
                    task_type="first_outreach",
                    payload={"to": "ceo@acme.test"},
                    rationale="yellow",
                )
            ],
        )
    )
    assert first.status == "awaiting_approval"
    assert calls["n"] == 0
    task = db_session.query(ManagerTask).one()
    assert task.approval_id is not None

    resolver.approve(
        ResolveApprovalRequest(approval_id=task.approval_id, resolved_by="owner", note="Send it")
    )
    resumed = agent.resume(first.manager_run_id)
    assert resumed.status == "succeeded"
    assert calls["n"] == 1
    assert any("approval_granted" in log for log in resumed.logs)


def test_manager_rejected_yellow_cancels(db_session, approval_settings):
    registry = RegistryExecutor()
    registry.register(
        "sales",
        "first_outreach",
        lambda p, t: DelegationResult(status="succeeded", summary="x", output={}),
    )
    svc = ApprovalService(db_session, approval_settings)
    resolver = ApprovalResolver(db_session, approval_settings, service=svc)
    agent = ManagerAgent(
        session=db_session,
        executor=registry,
        settings=approval_settings,
        approval_service=svc,
    )
    first = agent.run(
        ManagerRequest(
            goal="Outreach",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="sales",
                    task_type="first_outreach",
                    payload={"to": "x@y.z"},
                    rationale="yellow",
                )
            ],
        )
    )
    task = db_session.query(ManagerTask).one()
    resolver.reject(
        ResolveApprovalRequest(approval_id=task.approval_id, resolved_by="admin", note="No")
    )
    resumed = agent.resume(first.manager_run_id)
    assert resumed.status == "failed"
    db_session.refresh(task)
    assert task.status == ManagerTaskStatus.CANCELLED


def test_red_never_executed_by_manager_even_if_approved(db_session, approval_settings):
    registry = RegistryExecutor()
    registry.register(
        "finance",
        "money_transfer",
        lambda p, t: DelegationResult(status="succeeded", summary="paid", output={}),
    )
    svc = ApprovalService(db_session, approval_settings)
    resolver = ApprovalResolver(db_session, approval_settings, service=svc)
    agent = ManagerAgent(
        session=db_session,
        executor=registry,
        settings=approval_settings,
        approval_service=svc,
    )
    first = agent.run(
        ManagerRequest(
            goal="Pay",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="finance",
                    task_type="money_transfer",
                    payload={"amount": 50},
                    rationale="red",
                )
            ],
        )
    )
    task = db_session.query(ManagerTask).one()
    resolver.approve(
        ResolveApprovalRequest(approval_id=task.approval_id, resolved_by="owner", note="ok")
    )
    resumed = agent.resume(first.manager_run_id)
    assert resumed.status == "failed"
    db_session.refresh(task)
    assert task.status == ManagerTaskStatus.CANCELLED
    assert task.error_message == "human_only_not_agent_executable"


def test_approval_events_auditable(approval_svc, resolver, db_session):
    view = approval_svc.request_approval(
        ApprovalRequest(
            action_type="commerce.purchase",
            description="Buy supplies",
            requested_by="manager",
            action_payload={"item": "paper"},
        )
    )
    db_session.commit()
    resolver.approve(ResolveApprovalRequest(approval_id=view.id, resolved_by="owner"))
    events = db_session.query(ApprovalEvent).filter(ApprovalEvent.approval_id == view.id).all()
    types = {e.event_type for e in events}
    assert "requested" in types
    assert "approved" in types
