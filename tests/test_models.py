from decimal import Decimal

from sqlalchemy import inspect

from app.database import get_engine, get_session_factory
from models import (
    AgentRun,
    Approval,
    Company,
    CostEntry,
    Customer,
    DailyMetric,
    DeliveryProject,
    Experiment,
    Lead,
    Report,
    RevenueEntry,
    Task,
)
from models.enums import (
    AgentName,
    ApprovalType,
    CostCategory,
    Industry,
    LeadStatus,
)


def test_all_expected_tables_exist(app) -> None:
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    assert tables == {
        "agent_runs",
        "approvals",
        "companies",
        "cost_entries",
        "customers",
        "daily_metrics",
        "delivery_projects",
        "experiments",
        "leads",
        "reports",
        "revenue_entries",
        "tasks",
    }


def test_company_lead_score_and_related_records(app) -> None:
    session = get_session_factory()()
    try:
        company = Company(
            name="Harbor Cleaning Co",
            website_url="https://harborcleaning.example",
            industry=Industry.CLEANING,
            city="Rotterdam",
            country="NL",
            source="manual",
        )
        session.add(company)
        session.flush()

        lead = Lead(
            company_id=company.id,
            status=LeadStatus.SCORED,
            website_quality_score=16,
            online_presence_score=14,
            lead_capture_score=12,
            automation_potential_score=18,
            commercial_potential_score=15,
            total_score=75,
            contact_email="info@harborcleaning.example",
        )
        session.add(lead)
        session.flush()

        customer = Customer(company_id=company.id, lead_id=lead.id)
        session.add(customer)
        session.flush()

        project = DeliveryProject(customer_id=customer.id, name="Booking form automation")
        session.add(project)
        session.flush()

        run = AgentRun(
            agent_name=AgentName.RESEARCH,
            company_id=company.id,
            lead_id=lead.id,
            idempotency_key="research-harbor-1",
        )
        session.add(run)
        session.flush()

        session.add_all(
            [
                Task(title="Confirm booking form fields", delivery_project_id=project.id),
                Approval(
                    approval_type=ApprovalType.FIRST_EXTERNAL_OUTREACH,
                    summary="First email to Harbor Cleaning Co",
                    requested_by_agent=AgentName.SALES,
                    lead_id=lead.id,
                    idempotency_key="outreach-harbor-1",
                ),
                CostEntry(category=CostCategory.AI, amount_usd=Decimal("0.1200"), agent_run_id=run.id),
                RevenueEntry(amount_usd=Decimal("750.00"), customer_id=customer.id),
                DailyMetric(metric_date=lead.created_at.date(), leads_created=1, leads_scored=1),
                Report(title="Phase 1 smoke report", content="No agent activity yet."),
                Experiment(name="homepage-cta-v1", hypothesis="A clearer CTA increases inquiries."),
            ]
        )
        session.commit()

        stored = session.get(Lead, lead.id)
        assert stored is not None
        assert stored.company.name == "Harbor Cleaning Co"
        assert stored.total_score == 75
        assert stored.website_quality_score <= 20
        assert stored.customer is not None
        assert stored.customer.delivery_projects[0].name == "Booking form automation"
    finally:
        session.close()
