"""Phase 19 — end-to-end autonomous business cycle integration tests.

Uses mocked specialist executors + real ManagerAgent / SQLite persistence.
Never hits external providers. Never auto-approves YELLOW outreach.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents.manager import (
    ManagerAgent,
    ManagerRequest,
    PlannedTaskSpec,
    RegistryExecutor,
)
from app.agents.manager.cycle import parse_cycle_goal, recommend_next_strategy
from app.agents.manager.planner import create_plan
from app.agents.manager.schemas import BusinessStateSnapshot, DelegationResult
from app.config import Settings
from app.models import Approval, ManagerRun
from app.models.enums import (
    ApprovalStatus,
    ManagerDecisionType,
    ManagerRunStatus,
    ManagerTaskStatus,
    RiskLevel,
)


@pytest.fixture()
def cycle_settings(settings) -> Settings:
    return Settings(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        max_agent_runtime_seconds=60,
        max_retries=1,
        max_tasks_per_run=20,
        max_ai_cost_per_run=Decimal("5.00"),
        approval_required_for_external_actions=True,
        max_companies_per_run=20,
        max_audits_per_run=10,
        max_outbound_messages_per_day=5,
    )


def _ok(summary: str, output: dict | None = None) -> DelegationResult:
    return DelegationResult(
        status="succeeded",
        summary=summary,
        estimated_cost=Decimal("0"),
        output=output or {"ok": True},
        retryable=False,
    )


def _full_cycle_executor(overrides: dict | None = None) -> RegistryExecutor:
    registry = RegistryExecutor()
    defaults: dict[tuple[str, str], object] = {
        ("research", "discover_companies"): lambda p, t: _ok(
            "discovered", {"companies_created": 3}
        ),
        ("scoring", "score_companies"): lambda p, t: _ok("scored", {"scored_count": 3}),
        ("audit", "audit_digital_presence"): lambda p, t: _ok(
            "audited", {"audits_completed": 2}
        ),
        ("sales", "draft_outreach"): lambda p, t: _ok(
            "drafted", {"outreach_id": "00000000-0000-4000-8000-000000000001"}
        ),
        ("sales", "send_outreach"): lambda p, t: _ok(
            "sent", {"outreach_id": str(p.get("outreach_id"))}
        ),
        ("sales", "first_outreach"): lambda p, t: _ok("first", {"outreach_id": "x"}),
        ("followup", "process_due"): lambda p, t: _ok("followups", {"processed": 0}),
        ("responses", "monitor"): lambda p, t: _ok(
            "monitored", {"responses_recorded": 1}
        ),
        ("delivery", "create_project"): lambda p, t: _ok(
            "project",
            {
                "project_id": "00000000-0000-4000-8000-000000000002",
                "customer_id": "00000000-0000-4000-8000-000000000003",
            },
        ),
        ("finance", "calculate_metrics"): lambda p, t: _ok(
            "metrics",
            {
                "metric_id": "00000000-0000-4000-8000-000000000004",
                "profit": "100",
                "mrr": "1000",
                "roi": "2.5",
            },
        ),
        ("report", "generate"): lambda p, t: _ok(
            "report", {"report_id": "00000000-0000-4000-8000-000000000005"}
        ),
        ("learning", "evaluate_performance"): lambda p, t: _ok(
            "learned",
            {
                "recommendations": ["continue_pipeline"],
                "priorities": ["pipeline"],
                "goal_met": False,
            },
        ),
        ("strategy", "major_change"): lambda p, t: _ok("strategy", {"recorded": True}),
    }
    if overrides:
        defaults.update(overrides)
    for (agent_name, task_type), handler in defaults.items():
        registry.register(agent_name, task_type, handler)  # type: ignore[arg-type]
    return registry


def test_parse_mrr_cycle_goal():
    goal = parse_cycle_goal(
        "Reach €1,000 MRR while keeping operating costs below €150/month."
    )
    assert goal.full_cycle is True
    assert goal.target_mrr == Decimal("1000")
    assert goal.max_monthly_operating_cost == Decimal("150")
    assert goal.currency_hint == "EUR"


def test_planner_full_cycle_stages(cycle_settings):
    state = BusinessStateSnapshot(
        companies_total=5,
        qualified_leads=2,
        unscored_company_ids=["a"],
        unaudited_company_ids=["b"],
        qualified_unaudited_count=1,
        draftable_leads=[{"lead_id": "l1", "company_id": "c1"}],
        draftable_leads_count=1,
        draft_outreach_ids=["o1"],
        pending_outreach_drafts=1,
        follow_ups_due=1,
        converted_lead_ids=["l2"],
        converted_leads_without_project=1,
    )
    plan = create_plan(
        ManagerRequest(
            goal="Reach €1,000 MRR while keeping operating costs below €150/month."
        ),
        state,
        cycle_settings,
    )
    pairs = [(t.agent_name, t.task_type) for t in plan.tasks]
    assert ("research", "discover_companies") in pairs
    assert ("scoring", "score_companies") in pairs
    assert ("audit", "audit_digital_presence") in pairs
    assert ("sales", "draft_outreach") in pairs
    assert ("sales", "send_outreach") in pairs
    assert ("followup", "process_due") in pairs
    assert ("responses", "monitor") in pairs
    assert ("delivery", "create_project") in pairs
    assert ("finance", "calculate_metrics") in pairs
    assert ("report", "generate") in pairs
    assert ("learning", "evaluate_performance") in pairs
    assert plan.full_cycle is True
    assert len(plan.tasks) <= cycle_settings.max_tasks_per_run


def test_planner_lead_only_excludes_outbound(cycle_settings):
    state = BusinessStateSnapshot(companies_total=0, qualified_leads=0)
    plan = create_plan(
        ManagerRequest(goal="Generate 20 qualified local business leads.", location="Berlin"),
        state,
        cycle_settings,
    )
    pairs = [(t.agent_name, t.task_type) for t in plan.tasks]
    assert ("research", "discover_companies") in pairs
    assert ("scoring", "score_companies") in pairs
    assert ("sales", "send_outreach") not in pairs
    assert ("learning", "evaluate_performance") not in pairs


def test_planner_cost_cap_blocks_outbound(cycle_settings):
    state = BusinessStateSnapshot(
        companies_total=5,
        qualified_leads=5,
        draftable_leads=[{"lead_id": "l1", "company_id": "c1"}],
        draftable_leads_count=1,
        draft_outreach_ids=["o1"],
        pending_outreach_drafts=1,
        operating_costs_mtd=Decimal("200"),
    )
    plan = create_plan(
        ManagerRequest(
            goal="Reach €1,000 MRR while keeping operating costs below €150/month."
        ),
        state,
        cycle_settings,
    )
    pairs = [(t.agent_name, t.task_type) for t in plan.tasks]
    assert ("sales", "draft_outreach") not in pairs
    assert ("sales", "send_outreach") not in pairs
    assert "Outbound paused" in plan.summary


def test_learning_recommendations_traceable():
    state = BusinessStateSnapshot(
        qualified_leads=2,
        mrr=Decimal("100"),
        pending_approvals=1,
        draftable_leads_count=2,
    )
    goal = parse_cycle_goal("Reach €1,000 MRR while keeping operating costs below €150/month.")
    rec = recommend_next_strategy(goal=goal, state=state)
    assert rec["goal_met"] is False
    assert rec["recommendations"]
    assert "approvals_queue" in rec["priorities"] or "sales_draft" in rec["priorities"]


def test_e2e_full_cycle_force_tasks_traceable(db_session, cycle_settings):
    """Forced full-cycle task list: all stages execute, decisions logged, finite stop."""
    agent = ManagerAgent(
        session=db_session,
        executor=_full_cycle_executor(),
        settings=cycle_settings,
    )
    stages = [
        ("research", "discover_companies", {"query": "berlin"}),
        ("scoring", "score_companies", {"score_all_unscored": True}),
        ("audit", "audit_digital_presence", {"max_audits": 2}),
        (
            "sales",
            "draft_outreach",
            {
                "company_id": "00000000-0000-4000-8000-000000000010",
                "lead_id": "00000000-0000-4000-8000-000000000011",
            },
        ),
        ("responses", "monitor", {}),
        ("finance", "calculate_metrics", {"currency": "EUR"}),
        ("report", "generate", {"period_type": "daily"}),
        (
            "learning",
            "evaluate_performance",
            {"target_qualified_leads": 10, "target_mrr": "1000"},
        ),
    ]
    result = agent.run(
        ManagerRequest(
            goal="Reach €1,000 MRR while keeping operating costs below €150/month.",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name=a,
                    task_type=t,
                    payload=p,
                    rationale=f"e2e {a}/{t}",
                )
                for a, t, p in stages
            ],
            metadata={"full_cycle": True},
        )
    )
    assert result.status == "succeeded"
    assert result.stop_reason in {"plan_complete", "goal_met", "partial_progress"}
    assert result.tasks_succeeded == len(stages)
    assert result.tasks_failed == 0

    run = db_session.get(ManagerRun, result.manager_run_id)
    assert run is not None
    assert run.status == ManagerRunStatus.SUCCEEDED
    assert len(run.tasks) == len(stages)
    assert all(t.status == ManagerTaskStatus.SUCCEEDED.value for t in run.tasks)
    assert all(t.verified for t in run.tasks)

    decision_types = {d.decision_type for d in result.decisions}
    assert ManagerDecisionType.PLAN_CREATED.value in decision_types
    assert ManagerDecisionType.DELEGATE.value in decision_types
    assert ManagerDecisionType.EXECUTE.value in decision_types
    assert ManagerDecisionType.VERIFY.value in decision_types
    assert ManagerDecisionType.MEASURE.value in decision_types
    assert ManagerDecisionType.COMPLETE.value in decision_types

    for task in run.tasks:
        assert task.result_payload is not None
        assert task.result_summary


def test_e2e_yellow_outreach_stops_for_approval(db_session, cycle_settings):
    """YELLOW send_outreach must request approval and stop — never bypass."""
    calls = {"send": 0}

    def boom_send(payload, timeout):
        calls["send"] += 1
        return _ok("should_not_run", {})

    agent = ManagerAgent(
        session=db_session,
        executor=_full_cycle_executor({("sales", "send_outreach"): boom_send}),
        settings=cycle_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Reach €1,000 MRR",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="sales",
                    task_type="send_outreach",
                    payload={"outreach_id": "00000000-0000-4000-8000-000000000099"},
                    rationale="e2e approval gate",
                )
            ],
        )
    )
    assert result.status == "awaiting_approval"
    assert result.stop_reason == "awaiting_approval"
    assert calls["send"] == 0

    run = db_session.get(ManagerRun, result.manager_run_id)
    assert run is not None
    assert run.status == ManagerRunStatus.AWAITING_APPROVAL
    task = run.tasks[0]
    assert task.status == ManagerTaskStatus.AWAITING_APPROVAL.value
    assert task.approval_id is not None
    approval = db_session.get(Approval, task.approval_id)
    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.risk_level in {RiskLevel.YELLOW, RiskLevel.YELLOW.value}


def test_e2e_runtime_limit_stops_cycle(db_session, cycle_settings):
    """Safe stop: runtime limit prevents unbounded execution mid-cycle."""
    limited = cycle_settings.model_copy(update={"max_agent_runtime_seconds": 0})
    clock = {"t": 0.0}

    def tick():
        clock["t"] += 10.0
        return clock["t"]

    agent = ManagerAgent(
        session=db_session,
        executor=_full_cycle_executor(),
        settings=limited,
        clock=tick,
    )
    result = agent.run(
        ManagerRequest(
            goal="Reach €1,000 MRR",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="research",
                    task_type="discover_companies",
                    payload={"query": "x"},
                    rationale="will hit runtime",
                ),
                PlannedTaskSpec(
                    agent_name="learning",
                    task_type="evaluate_performance",
                    payload={},
                    rationale="should not always finish",
                ),
            ],
        )
    )
    assert result.status == "stopped"
    assert result.stop_reason == "runtime_limit"


def test_e2e_red_task_never_executes(db_session, cycle_settings):
    calls = {"n": 0}

    def should_not_run(payload, timeout):
        calls["n"] += 1
        return _ok("nope")

    registry = RegistryExecutor()
    registry.register("finance", "money_transfer", should_not_run)
    agent = ManagerAgent(
        session=db_session,
        executor=registry,
        settings=cycle_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Transfer funds",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="finance",
                    task_type="money_transfer",
                    payload={"amount": "100"},
                    rationale="red action",
                )
            ],
        )
    )
    assert calls["n"] == 0
    assert result.status in {"awaiting_approval", "succeeded", "failed", "stopped"}
    run = db_session.get(ManagerRun, result.manager_run_id)
    assert run is not None
    # RED: approval may be requested then cancelled as human-only, or cancelled directly
    task = run.tasks[0]
    assert task.status in {
        ManagerTaskStatus.CANCELLED.value,
        ManagerTaskStatus.AWAITING_APPROVAL.value,
        ManagerTaskStatus.INVALID.value,
    }
