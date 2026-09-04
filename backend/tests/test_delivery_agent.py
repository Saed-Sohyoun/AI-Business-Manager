"""Phase 13 — Delivery Agent and customer project system tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.agents.delivery import DeliveryAgent, DeliveryRequest, TaskSpec
from app.approvals import ApprovalResolver, ApprovalService, ResolveApprovalRequest
from app.config import Settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.models import (
    AgentRun,
    Company,
    Customer,
    Deliverable,
    DeliveryActivity,
    DeliveryProject,
    Lead,
    ProjectTask,
)
from app.models.enums import (
    AgentRunStatus,
    CompanyStatus,
    CustomerStatus,
    DeliverableStatus,
    DeliveryProjectStatus,
    LeadScoreCategory,
    LeadStatus,
    ProjectTaskStatus,
)


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        approval_authorized_resolvers="owner,admin",
        approval_default_ttl_seconds=3600,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def delivery_env(db_session):
    cfg = _settings()
    company = Company(name="Acme Co", status=CompanyStatus.PROSPECT, source="test")
    db_session.add(company)
    db_session.flush()
    lead = Lead(
        company_id=company.id,
        name="Alex Rivera",
        email="alex@acme.example",
        status=LeadStatus.QUALIFIED,
        score_category=LeadScoreCategory.HOT,
    )
    db_session.add(lead)
    db_session.commit()

    approvals = ApprovalService(db_session, cfg)
    resolver = ApprovalResolver(db_session, cfg, service=approvals)
    agent = DeliveryAgent(session=db_session, settings=cfg, approval_service=approvals)
    return {
        "session": db_session,
        "settings": cfg,
        "company": company,
        "lead": lead,
        "approvals": approvals,
        "resolver": resolver,
        "agent": agent,
    }


def test_lifecycle_lead_to_project_with_tasks(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(
        DeliveryRequest(
            lead_id=delivery_env["lead"].id,
            project_name="Website refresh",
            idempotency_key="delivery-run-1",
        )
    )
    assert result.status == "succeeded"
    assert result.customer_id is not None
    assert result.project_id is not None
    assert len(result.tasks) == 5

    lead = delivery_env["session"].get(Lead, delivery_env["lead"].id)
    assert lead.status == LeadStatus.CONVERTED

    customer = delivery_env["session"].get(Customer, result.customer_id)
    assert customer.status == CustomerStatus.ACTIVE
    assert customer.lead_id == lead.id

    project = delivery_env["session"].get(DeliveryProject, result.project_id)
    assert project.status == DeliveryProjectStatus.ACTIVE
    assert project.name == "Website refresh"

    run = delivery_env["session"].get(AgentRun, result.agent_run_id)
    assert run.agent_name == "delivery"
    assert run.status == AgentRunStatus.SUCCEEDED

    kickoff = next(t for t in result.tasks if t.task_key == "kickoff")
    requirements = next(t for t in result.tasks if t.task_key == "requirements")
    handoff = next(t for t in result.tasks if t.task_key == "customer_handoff")
    assert requirements.depends_on == ["kickoff"]
    assert handoff.is_sensitive is True
    assert kickoff.status == ProjectTaskStatus.PENDING.value


def test_idempotent_run(delivery_env):
    agent = delivery_env["agent"]
    req = DeliveryRequest(
        lead_id=delivery_env["lead"].id,
        idempotency_key="delivery-idem-1",
    )
    first = agent.run(req)
    second = agent.run(req)
    assert first.project_id == second.project_id
    assert second.idempotent_replay is True
    projects = list(delivery_env["session"].scalars(select(DeliveryProject)))
    customers = list(delivery_env["session"].scalars(select(Customer)))
    assert len(projects) == 1
    assert len(customers) == 1


def test_task_dependencies_block_execution(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(DeliveryRequest(lead_id=delivery_env["lead"].id))
    req_task = next(t for t in result.tasks if t.task_key == "requirements")

    with pytest.raises(ValidationAppError, match="dependencies"):
        agent.execute_task(req_task.id)

    blocked = delivery_env["session"].get(ProjectTask, req_task.id)
    assert blocked.status == ProjectTaskStatus.BLOCKED


def test_execute_verify_complete_safe_task(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(DeliveryRequest(lead_id=delivery_env["lead"].id))
    kickoff = next(t for t in result.tasks if t.task_key == "kickoff")

    executed = agent.execute_task(kickoff.id, notes="scoped")
    assert executed.status == ProjectTaskStatus.REVIEW
    assert executed.verified is False

    with pytest.raises(ForbiddenError, match="verification"):
        agent.complete_task_without_verification(kickoff.id)

    with pytest.raises(ValidationAppError, match="notes"):
        agent.verify_task(kickoff.id, notes="  ")

    verified = agent.verify_task(kickoff.id, notes="Scope confirmed with customer")
    assert verified.status == ProjectTaskStatus.COMPLETED
    assert verified.verified is True
    assert verified.verified_at is not None

    project = delivery_env["session"].get(DeliveryProject, result.project_id)
    assert project.status == DeliveryProjectStatus.DELIVERY


def test_never_complete_project_without_verification(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(DeliveryRequest(lead_id=delivery_env["lead"].id))

    with pytest.raises(ForbiddenError, match="verification"):
        agent.complete_project(result.project_id)

    # Execute+verify all safe tasks except sensitive handoff still not enough to complete
    tasks = {
        t.task_key: t
        for t in delivery_env["session"].scalars(
            select(ProjectTask).where(ProjectTask.project_id == result.project_id)
        )
    }
    for key in ("kickoff", "requirements", "draft_deliverable", "internal_review"):
        agent.execute_task(tasks[key].id)
        agent.verify_task(tasks[key].id, notes=f"ok {key}")
        delivery_env["session"].refresh(tasks[key])

    with pytest.raises(ForbiddenError, match="verification"):
        agent.complete_project(result.project_id)


def test_sensitive_task_requires_approval(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(DeliveryRequest(lead_id=delivery_env["lead"].id))
    tasks = {
        t.task_key: delivery_env["session"].get(ProjectTask, t.id)
        for t in result.tasks
    }
    for key in ("kickoff", "requirements", "draft_deliverable", "internal_review"):
        agent.execute_task(tasks[key].id)
        agent.verify_task(tasks[key].id, notes=f"verified {key}")

    handoff = tasks["customer_handoff"]
    with pytest.raises(ForbiddenError, match="approval"):
        agent.execute_task(handoff.id)

    approval_id = agent.request_sensitive_approval(handoff.id)
    delivery_env["resolver"].approve(
        ResolveApprovalRequest(approval_id=approval_id, resolved_by="owner", note="ok")
    )
    executed = agent.execute_task(handoff.id, notes="handoff package")
    assert executed.status == ProjectTaskStatus.REVIEW

    agent.verify_task(handoff.id, notes="Customer received package")
    project = agent.verify_project(result.project_id, notes="All deliverables checked")
    assert project.verified is True
    assert project.status == DeliveryProjectStatus.VERIFICATION

    completed = agent.complete_project(result.project_id)
    assert completed.status == DeliveryProjectStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.progress_percent == 100


def test_produce_deliverable_and_activity_log(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(DeliveryRequest(lead_id=delivery_env["lead"].id))
    kickoff = next(t for t in result.tasks if t.task_key == "kickoff")
    agent.execute_task(kickoff.id)

    d1 = agent.produce_deliverable(
        project_id=result.project_id,
        title="Scope doc",
        content="Agreed scope...",
        task_id=kickoff.id,
        idempotency_key=f"deliv:{result.project_id}:scope",
    )
    d2 = agent.produce_deliverable(
        project_id=result.project_id,
        title="Scope doc",
        content="Agreed scope...",
        task_id=kickoff.id,
        idempotency_key=f"deliv:{result.project_id}:scope",
    )
    assert d1.id == d2.id
    assert d1.status == DeliverableStatus.DRAFT

    verified = agent.verify_deliverable(d1.id, notes="content looks good")
    assert verified.verified is True
    assert verified.status == DeliverableStatus.READY

    activities = agent.list_activities(result.project_id)
    types = {a.activity_type for a in activities}
    assert "project_created" in types
    assert "tasks_created" in types
    assert "task_executed" in types
    assert "deliverable_produced" in types
    assert "deliverable_verified" in types

    progress = agent.get_progress(result.project_id)
    assert progress.deliverable_count == 1
    assert progress.total_tasks == 5


def test_custom_tasks_with_dependencies(delivery_env):
    agent = delivery_env["agent"]
    result = agent.run(
        DeliveryRequest(
            lead_id=delivery_env["lead"].id,
            tasks=[
                TaskSpec(task_key="a", title="A", depends_on=[], sort_order=1),
                TaskSpec(task_key="b", title="B", depends_on=["a"], sort_order=2),
            ],
        )
    )
    assert len(result.tasks) == 2
    b = next(t for t in result.tasks if t.task_key == "b")
    assert b.depends_on == ["a"]
