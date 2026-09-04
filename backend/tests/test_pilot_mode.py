"""Phase 22 — Pilot Mode limits, budget, execution guard, production unlock."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.approvals import ApprovalService
from app.config import Settings, clear_settings_cache
from app.exceptions import ForbiddenError, LimitReachedError
from app.models import Company, CompanyAudit, OutboundMessage
from app.models.enums import (
    AuditPriority,
    AuditStatus,
    CompanyStatus,
    CostCategory,
    OutboundMessageStatus,
)
from app.pilot import (
    BudgetGuard,
    ExecutionGuard,
    LimitService,
    pilot_mode_from_settings,
)
from app.pilot.budget import utc_day_key


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        operating_mode="pilot",
        allow_production_mode=False,
        max_companies_per_day=20,
        max_audits_per_day=10,
        max_initial_outreach_per_day=5,
        max_followups=2,
        daily_budget_limit=Decimal("3.00"),
        max_single_expense=Decimal("20.00"),
        budget_warning_ratio=Decimal("0.80"),
        pilot_currency="EUR",
        approval_authorized_resolvers="owner,admin",
        max_outbound_messages_per_day=5,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def pilot_env(db_session):
    cfg = _settings()
    limits = LimitService(db_session, cfg)
    budget = BudgetGuard(db_session, cfg)
    guard = ExecutionGuard(db_session, cfg, limits=limits, budget=budget)
    return {
        "session": db_session,
        "settings": cfg,
        "limits": limits,
        "budget": budget,
        "guard": guard,
    }


def _company(session, name: str) -> Company:
    row = Company(name=name, status=CompanyStatus.PROSPECT, source="pilot-test")
    session.add(row)
    session.flush()
    return row


def _audit(session, company_id) -> CompanyAudit:
    row = CompanyAudit(
        company_id=company_id,
        status=AuditStatus.SUCCEEDED,
        priority=AuditPriority.MEDIUM,
        audit_version="1",
        summary="pilot",
        problems=[],
        opportunities=[],
        evidence_urls=[],
        observations={},
        evidence_catalog=[],
        audited_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def _initial_outbound(session, *, to_email: str) -> OutboundMessage:
    row = OutboundMessage(
        status=OutboundMessageStatus.SENT,
        idempotency_key=f"pilot-out-{uuid4().hex[:12]}",
        to_email=to_email,
        from_email="ops@example.com",
        subject="Hi",
        body_text="Hello",
        provider="test",
        is_followup=False,
        followup_index=0,
        sent_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


# --- Config / accidental production -------------------------------------------


def test_pilot_defaults_match_phase22():
    cfg = _settings()
    pilot = pilot_mode_from_settings(cfg)
    assert pilot.enabled is True
    assert pilot.max_companies_per_day == 20
    assert pilot.max_audits_per_day == 10
    assert pilot.max_initial_outreach_per_day == 5
    assert pilot.max_followups_per_lead == 2
    assert pilot.max_daily_spending == Decimal("3.00")
    assert pilot.max_single_expense == Decimal("20.00")
    assert pilot.currency == "EUR"
    assert "sales.first_outreach" in pilot.approval_required_actions
    assert "commerce.purchase" in pilot.approval_required_actions
    assert "commerce.discount" in pilot.approval_required_actions
    assert "legal.contract" in pilot.approval_required_actions
    assert "strategy.major_change" in pilot.approval_required_actions


def test_production_mode_requires_explicit_unlock():
    with pytest.raises(ValidationError):
        Settings(
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            operating_mode="production",
            allow_production_mode=False,
        )
    cfg = Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        operating_mode="production",
        allow_production_mode=True,
        daily_budget_limit=Decimal("100"),
    )
    assert cfg.is_pilot_mode is False


def test_settings_defaults_are_pilot_safe():
    clear_settings_cache()
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        app_env="test",
    )
    assert settings.operating_mode == "pilot"
    assert settings.daily_budget_limit == Decimal("3.00")
    assert settings.max_single_expense == Decimal("20.00")
    assert settings.max_companies_per_day == 20
    assert settings.max_audits_per_day == 10
    assert settings.max_initial_outreach_per_day == 5


# --- LimitService: every limit ------------------------------------------------


def test_companies_per_day_limit(pilot_env):
    session = pilot_env["session"]
    limits: LimitService = pilot_env["limits"]
    cfg = _settings(max_companies_per_day=2)
    limits = LimitService(session, cfg)
    _company(session, "A")
    _company(session, "B")
    session.commit()
    check = limits.check_companies(additional=1)
    assert check.allowed is False
    assert check.limit_name == "companies_per_day"
    with pytest.raises(LimitReachedError):
        limits.assert_companies()


def test_audits_per_day_limit(pilot_env):
    session = pilot_env["session"]
    cfg = _settings(max_audits_per_day=1)
    limits = LimitService(session, cfg)
    company = _company(session, "Audited Co")
    _audit(session, company.id)
    session.commit()
    with pytest.raises(LimitReachedError) as exc:
        limits.assert_audits()
    assert exc.value.details["limit_name"] == "audits_per_day"


def test_initial_outreach_per_day_limit(pilot_env):
    session = pilot_env["session"]
    cfg = _settings(max_initial_outreach_per_day=2)
    limits = LimitService(session, cfg)
    _initial_outbound(session, to_email="a@example.com")
    _initial_outbound(session, to_email="b@example.com")
    session.commit()
    with pytest.raises(LimitReachedError):
        limits.assert_initial_outreach()


def test_followups_per_lead_limit(pilot_env):
    session = pilot_env["session"]
    cfg = _settings(max_followups=2)
    limits = LimitService(session, cfg)
    lead_id = uuid4()
    for i in range(2):
        session.add(
            OutboundMessage(
                status=OutboundMessageStatus.SENT,
                idempotency_key=f"fu-{i}-{uuid4().hex[:8]}",
                to_email="lead@example.com",
                from_email="ops@example.com",
                subject="FU",
                body_text="follow",
                provider="test",
                lead_id=lead_id,
                is_followup=True,
                followup_index=i + 1,
                sent_at=datetime.now(timezone.utc),
            )
        )
    session.commit()
    with pytest.raises(LimitReachedError):
        limits.assert_followups_for_lead(lead_id)


# --- BudgetGuard --------------------------------------------------------------


def test_max_single_expense_limit(pilot_env):
    budget: BudgetGuard = pilot_env["budget"]
    with pytest.raises(LimitReachedError):
        budget.assert_can_spend(Decimal("20.01"))
    # Single-expense ceiling alone (daily checked separately)
    ok = budget.check_single_expense(Decimal("20.00"))
    assert ok.allowed is True
    with pytest.raises(LimitReachedError):
        # 20 exceeds daily pilot spend of 3
        budget.assert_can_spend(Decimal("20.00"))


def test_daily_spending_limit(pilot_env, db_session):
    from app.agents.finance import CostRecordRequest, FinanceAgent

    cfg = _settings(daily_budget_limit=Decimal("3.00"), max_single_expense=Decimal("20"))
    agent = FinanceAgent(
        session=db_session,
        settings=cfg,
        approval_service=ApprovalService(db_session, cfg),
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("2.50"),
            category=CostCategory.AI,
            source="pilot",
            idempotency_key="pilot-cost-1",
        )
    )
    with pytest.raises(LimitReachedError):
        agent.record_cost(
            CostRecordRequest(
                amount=Decimal("1.00"),
                category=CostCategory.AI,
                source="pilot",
                idempotency_key="pilot-cost-2",
            )
        )


def test_budget_warning_threshold(pilot_env, db_session):
    from app.agents.finance import CostRecordRequest, FinanceAgent

    notes: list[str] = []

    class FakeNotify:
        def notify_budget_warning(self, *, message: str, reference: str):
            notes.append(reference)
            return None

        def try_notify(self, **kwargs):
            return None

    cfg = _settings(
        daily_budget_limit=Decimal("3.00"),
        max_single_expense=Decimal("20"),
        budget_warning_ratio=Decimal("0.80"),
    )
    budget = BudgetGuard(db_session, cfg, notifications=FakeNotify())  # type: ignore[arg-type]
    agent = FinanceAgent(
        session=db_session,
        settings=cfg,
        approval_service=ApprovalService(db_session, cfg),
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("2.50"),
            category=CostCategory.SEARCH,
            source="pilot",
            idempotency_key="pilot-warn-1",
        )
    )
    # Recording goes through BudgetGuard.assert_expense_allowed only inside agent —
    # call guard directly after spend to emit warning.
    status = budget.assert_expense_allowed(Decimal("0"))
    assert status.warning is True
    assert any(r.startswith("pilot-budget-") for r in notes)


# --- ExecutionGuard / approvals -----------------------------------------------


def test_execution_guard_blocks_first_outreach_without_approval(pilot_env):
    guard: ExecutionGuard = pilot_env["guard"]
    decision = guard.evaluate("sales.first_outreach")
    assert decision.allowed is False
    assert decision.requires_approval is True
    with pytest.raises(ForbiddenError):
        guard.assert_may_execute("sales.first_outreach")


@pytest.mark.parametrize(
    "action",
    [
        "commerce.purchase",
        "commerce.discount",
        "strategy.major_change",
        "legal.contract",
    ],
)
def test_execution_guard_requires_approval_for_sensitive_actions(pilot_env, action):
    guard: ExecutionGuard = pilot_env["guard"]
    decision = guard.evaluate(action)
    assert decision.allowed is False
    assert decision.requires_approval is True


def test_execution_guard_stops_on_company_limit(pilot_env):
    session = pilot_env["session"]
    cfg = _settings(max_companies_per_day=0)
    guard = ExecutionGuard(session, cfg)
    with pytest.raises(LimitReachedError):
        guard.assert_may_execute("research.discover_companies")


def test_pilot_status_endpoint():
    from fastapi.testclient import TestClient

    from app.database import get_engine, init_db, reset_db_state
    from app.main import create_app
    from app.models import Base
    from app.security.rate_limit import http_rate_limiter

    http_rate_limiter.reset()
    clear_settings_cache()
    reset_db_state()
    cfg = _settings()
    application = create_app(cfg)
    with TestClient(application) as client:
        Base.metadata.create_all(bind=get_engine())
        resp = client.get("/api/v1/pilot/status")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["pilot_mode"] is True
    assert body["operating_mode"] == "pilot"
    assert body["currency"] == "EUR"
    assert body["limits"]["max_companies_per_day"] == 20
    assert body["limits"]["max_audits_per_day"] == 10
    assert body["limits"]["max_initial_outreach_per_day"] == 5
    assert body["limits"]["max_followups_per_lead"] == 2
    assert body["limits"]["max_daily_spending"] == "3.00"
    assert body["limits"]["max_single_expense"] == "20.00"
    assert "sales.first_outreach" in body["approval_required_actions"]
    reset_db_state()
    clear_settings_cache()
    http_rate_limiter.reset()


def test_utc_day_key_format():
    assert len(utc_day_key()) == 10
