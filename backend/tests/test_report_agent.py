"""Phase 15 — ReportAgent CEO reports from real DB data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.agents.finance import CostRecordRequest, FinanceAgent, RevenueRecordRequest
from app.agents.report import ReportAgent, ReportRequest, resolve_period
from app.agents.report.composer import SECTION_SPECS
from app.approvals import ApprovalService
from app.config import Settings
from app.models import (
    BusinessReport,
    Company,
    CompanyScore,
    Lead,
    ManagerRun,
)
from app.models.enums import (
    CompanyStatus,
    CostCategory,
    LeadScoreCategory,
    LeadStatus,
    ManagerRunStatus,
    ReportPeriodType,
    ReportStatementKind,
    RevenueType,
    ScoreBand,
)


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        approval_authorized_resolvers="owner,admin",
        max_single_expense=Decimal("10000"),
        daily_budget_limit=Decimal("100000"),
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def report_env(db_session):
    cfg = _settings()
    approvals = ApprovalService(db_session, cfg)
    agent = ReportAgent(session=db_session, settings=cfg, approval_service=approvals)
    finance = FinanceAgent(session=db_session, settings=cfg, approval_service=approvals)
    return {
        "session": db_session,
        "settings": cfg,
        "agent": agent,
        "finance": finance,
        "approvals": approvals,
    }


def _day(d: int = 4) -> datetime:
    return datetime(2026, 9, d, 12, 0, tzinfo=timezone.utc)


def test_resolve_period_daily_weekly_monthly():
    as_of = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    d_start, d_end = resolve_period(ReportPeriodType.DAILY, as_of=as_of)
    assert d_start == datetime(2026, 9, 15, tzinfo=timezone.utc)
    assert d_end.day == 15

    w_start, w_end = resolve_period(ReportPeriodType.WEEKLY, as_of=as_of)
    assert w_end == as_of
    assert w_end - w_start == timedelta(days=7)

    m_start, m_end = resolve_period(ReportPeriodType.MONTHLY, as_of=as_of)
    assert m_start == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert m_end.month == 9


def test_empty_db_marks_finance_unavailable(report_env):
    result = report_env["agent"].run(
        ReportRequest(
            period_type=ReportPeriodType.DAILY,
            as_of=_day(4),
            idempotency_key="report-empty-1",
        )
    )
    assert result.status == "succeeded"
    assert result.report is not None
    assert len(result.report.sections) == 20

    by_id = {s.section_id: s for s in result.report.sections}
    assert by_id["revenue"].statements[0].kind == ReportStatementKind.UNAVAILABLE
    assert "unavailable" in by_id["revenue"].statements[0].text.lower()
    assert by_id["costs"].statements[0].kind == ReportStatementKind.UNAVAILABLE
    assert by_id["profit"].statements[0].kind == ReportStatementKind.UNAVAILABLE
    assert by_id["roi"].statements[0].kind == ReportStatementKind.UNAVAILABLE

    # Counts are facts (zeros), not fabricated non-zeros
    assert by_id["companies_researched"].statements[0].value == "0"
    assert by_id["qualified_leads"].statements[0].value == "0"


def test_report_uses_real_pipeline_and_finance_data(report_env):
    session = report_env["session"]
    company = Company(name="Acme High", status=CompanyStatus.PROSPECT, source="test")
    session.add(company)
    session.flush()
    lead = Lead(
        company_id=company.id,
        name="Alex",
        email="alex@acme.example",
        status=LeadStatus.QUALIFIED,
        score_category=LeadScoreCategory.HOT,
        replied_at=_day(4),
    )
    session.add(lead)
    session.add(
        CompanyScore(
            company_id=company.id,
            total_score=90,
            band=ScoreBand.HIGH,
            website_quality=20,
            online_presence=20,
            lead_capture_process=15,
            automation_potential=20,
            commercial_potential=15,
            scoring_version="1.0.0",
            reasons=[],
            evidence={},
        )
    )
    session.add(
        ManagerRun(
            goal="Find 10 qualified local business leads",
            status=ManagerRunStatus.SUCCEEDED,
            target_qualified_leads=10,
            measured_qualified_leads=1,
            tasks_succeeded=3,
            started_at=_day(4),
        )
    )
    session.commit()

    finance = report_env["finance"]
    finance.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("200.00"),
            source="invoice",
            revenue_type=RevenueType.ONE_TIME,
            occurred_at=_day(4),
            idempotency_key="rep-rev-1",
        )
    )
    finance.record_cost(
        CostRecordRequest(
            amount=Decimal("50.00"),
            category=CostCategory.AI,
            source="openai",
            occurred_at=_day(4),
            idempotency_key="rep-cost-1",
        )
    )

    result = report_env["agent"].run(
        ReportRequest(
            period_type=ReportPeriodType.DAILY,
            as_of=_day(4),
            idempotency_key="report-full-1",
        )
    )
    assert result.status == "succeeded"
    report = result.report
    assert report is not None
    by_id = {s.section_id: s for s in report.sections}

    assert "Find 10 qualified" in by_id["business_goal"].statements[0].text
    assert by_id["qualified_leads"].statements[0].value == "1"
    assert by_id["companies_researched"].statements[0].value == "1"
    assert by_id["replies"].statements[0].value == "1"
    assert by_id["revenue"].statements[0].kind == ReportStatementKind.FACT
    assert by_id["revenue"].statements[0].value == "200.000000"
    assert by_id["costs"].statements[0].value == "50.000000"
    assert by_id["profit"].statements[0].value == "150.000000"
    assert by_id["roi"].statements[0].value == "3.000000"
    assert any(
        s.kind == ReportStatementKind.FACT and "Acme High" in (s.text or "")
        for s in by_id["best_opportunities"].statements
    )

    # Kind separation present
    kinds = {s.kind for sec in report.sections for s in sec.statements}
    assert ReportStatementKind.FACT in kinds
    assert ReportStatementKind.INTERPRETATION in kinds
    assert ReportStatementKind.RECOMMENDATION in kinds

    # Persisted
    row = session.scalar(select(BusinessReport).limit(1))
    assert row is not None
    assert row.facts_snapshot.get("total_revenue") == "200.000000"
    assert row.extra_metadata.get("ai_used_for_numbers") is False


def test_idempotent_report(report_env):
    req = ReportRequest(
        period_type=ReportPeriodType.WEEKLY,
        as_of=_day(10),
        idempotency_key="report-idem-1",
    )
    first = report_env["agent"].run(req)
    second = report_env["agent"].run(req)
    assert first.report is not None and second.report is not None
    assert first.report.id == second.report.id
    assert second.idempotent_replay is True
    assert len(list(report_env["session"].scalars(select(BusinessReport)))) == 1


def test_weekly_and_monthly_summaries(report_env):
    weekly = report_env["agent"].run(
        ReportRequest(
            period_type=ReportPeriodType.WEEKLY,
            as_of=_day(10),
            idempotency_key="report-weekly",
        )
    )
    monthly = report_env["agent"].run(
        ReportRequest(
            period_type=ReportPeriodType.MONTHLY,
            as_of=_day(10),
            idempotency_key="report-monthly",
        )
    )
    assert weekly.status == "succeeded"
    assert monthly.status == "succeeded"
    assert weekly.report.period_type == ReportPeriodType.WEEKLY
    assert monthly.report.period_type == ReportPeriodType.MONTHLY
    assert "Weekly" in weekly.report.title
    assert "Monthly" in monthly.report.title
    assert len(weekly.report.sections) == len(SECTION_SPECS)


def test_never_fabricates_missing_revenue(report_env):
    # Only costs recorded — revenue must be UNAVAILABLE, profit still computable with 0 revenue
    report_env["finance"].record_cost(
        CostRecordRequest(
            amount=Decimal("10"),
            category=CostCategory.EMAIL,
            source="resend",
            occurred_at=_day(4),
            idempotency_key="only-cost",
        )
    )
    result = report_env["agent"].run(
        ReportRequest(
            period_type=ReportPeriodType.DAILY,
            as_of=_day(4),
            idempotency_key="report-cost-only",
        )
    )
    by_id = {s.section_id: s for s in result.report.sections}
    assert by_id["revenue"].statements[0].kind == ReportStatementKind.UNAVAILABLE
    assert by_id["costs"].statements[0].kind == ReportStatementKind.FACT
    assert by_id["profit"].statements[0].kind == ReportStatementKind.FACT
    assert by_id["profit"].statements[0].value == "-10.000000"
