"""Model import and relationship smoke tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import (
    AgentRun,
    Approval,
    Base,
    Company,
    DailyMetric,
    Lead,
)
from app.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    CompanyStatus,
    LeadScoreCategory,
    LeadStatus,
    RiskLevel,
)


def test_models_are_importable():
    assert Company.__tablename__ == "companies"
    assert Lead.__tablename__ == "leads"
    assert AgentRun.__tablename__ == "agent_runs"
    assert Approval.__tablename__ == "approvals"
    assert DailyMetric.__tablename__ == "daily_metrics"
    assert "companies" in Base.metadata.tables


def test_company_lead_relationship_persists(db_session):
    company = Company(
        name="Acme GmbH",
        website="https://acme.example",
        industry="Software",
        location="Berlin",
        status=CompanyStatus.PROSPECT,
        source="manual",
    )
    db_session.add(company)
    db_session.flush()

    lead = Lead(
        company_id=company.id,
        name="Alex Example",
        email="alex@acme.example",
        job_title="CEO",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    db_session.add(lead)
    db_session.commit()

    db_session.refresh(company)
    assert len(company.leads) == 1
    assert company.leads[0].email == "alex@acme.example"


def test_agent_run_approval_and_metrics_defaults(db_session):
    run = AgentRun(
        agent_name="research",
        task_type="company_lookup",
        status=AgentRunStatus.PENDING,
        input_summary="lookup acme",
    )
    approval = Approval(
        action_type="send_email",
        description="First outreach to lead",
        risk_level=RiskLevel.YELLOW,
        status=ApprovalStatus.PENDING,
        requested_by="manager_agent",
    )
    metric = DailyMetric(
        metric_date=date(2026, 9, 4),
        revenue=Decimal("0.00"),
        costs=Decimal("0.00"),
        profit=Decimal("0.00"),
    )
    db_session.add_all([run, approval, metric])
    db_session.commit()

    assert run.estimated_cost == Decimal("0")
    assert run.extra_metadata == {}
    assert approval.extra_metadata == {}
    assert metric.qualified_leads == 0
