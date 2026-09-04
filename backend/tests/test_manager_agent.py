"""Manager Agent orchestration tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents.manager import (
    ManagerAgent,
    ManagerRequest,
    PlannedTaskSpec,
    RegistryExecutor,
    can_transition,
    transition,
)
from app.agents.manager.limits import LimitSnapshot, can_retry, evaluate_stop
from app.agents.manager.planner import create_plan, parse_target_count
from app.agents.manager.schemas import BusinessStateSnapshot, DelegationResult
from app.agents.manager.state_machine import InvalidTaskTransition
from app.config import Settings
from app.models import Approval, ManagerDecision, ManagerRun, ManagerTask
from app.models.enums import (
    ApprovalStatus,
    ManagerDecisionType,
    ManagerRunStatus,
    ManagerTaskStatus,
    RiskLevel,
)


@pytest.fixture()
def manager_settings(settings) -> Settings:
    return Settings(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        max_agent_runtime_seconds=60,
        max_retries=2,
        max_tasks_per_run=10,
        max_ai_cost_per_run=Decimal("5.00"),
        approval_required_for_external_actions=True,
        max_companies_per_run=20,
        max_audits_per_run=10,
    )


def _ok_research(payload: dict, timeout: float) -> DelegationResult:
    return DelegationResult(
        status="succeeded",
        summary="discovered companies",
        estimated_cost=Decimal("0.02"),
        output={"companies_created": 5},
    )


def _ok_scoring(payload: dict, timeout: float) -> DelegationResult:
    return DelegationResult(
        status="succeeded",
        summary="scored companies",
        estimated_cost=Decimal("0"),
        output={"scored_count": 5},
    )


def _build_executor(**handlers) -> RegistryExecutor:
    registry = RegistryExecutor()
    registry.register("research", "discover_companies", handlers.get("research", _ok_research))
    registry.register("scoring", "score_companies", handlers.get("scoring", _ok_scoring))
    if "audit" in handlers:
        registry.register("audit", "audit_digital_presence", handlers["audit"])
    return registry


def test_state_machine_allows_and_rejects():
    assert can_transition(ManagerTaskStatus.PENDING, ManagerTaskStatus.READY)
    assert transition(ManagerTaskStatus.READY, ManagerTaskStatus.RUNNING) == ManagerTaskStatus.RUNNING
    with pytest.raises(InvalidTaskTransition):
        transition(ManagerTaskStatus.SUCCEEDED, ManagerTaskStatus.RUNNING)


def test_parse_target_and_plan(manager_settings):
    assert parse_target_count("Generate 20 qualified local business leads.", None) == 20
    state = BusinessStateSnapshot(companies_total=0, qualified_leads=0)
    plan = create_plan(
        ManagerRequest(goal="Generate 20 qualified local business leads.", location="Berlin"),
        state,
        manager_settings,
    )
    assert plan.target_qualified_leads == 20
    assert any(t.agent_name == "research" for t in plan.tasks)
    assert any(t.agent_name == "scoring" for t in plan.tasks)
    assert not any(t.agent_name == "sales" for t in plan.tasks)


def test_planning_and_delegation(db_session, manager_settings):
    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(),
        settings=manager_settings,
    )
    result = agent.run(
        ManagerRequest(goal="Generate 20 qualified local business leads.", location="Berlin")
    )
    assert result.status == "succeeded"
    assert result.tasks_created >= 2
    assert result.tasks_succeeded >= 2
    assert any(d.decision_type == ManagerDecisionType.PLAN_CREATED.value for d in result.decisions)
    assert any(d.decision_type == ManagerDecisionType.DELEGATE.value for d in result.decisions)
    assert any(d.decision_type == ManagerDecisionType.EXECUTE.value for d in result.decisions)
    run = db_session.get(ManagerRun, result.manager_run_id)
    assert run is not None
    assert run.status == ManagerRunStatus.SUCCEEDED
    assert len(run.tasks) >= 2


def test_failure_and_retry(db_session, manager_settings):
    attempts = {"n": 0}

    def flaky_research(payload: dict, timeout: float) -> DelegationResult:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return DelegationResult(
                status="failed",
                summary="transient search error",
                retryable=True,
                error_message="SearchTimeoutError",
            )
        return _ok_research(payload, timeout)

    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(research=flaky_research),
        settings=manager_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Generate 5 qualified leads",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="research",
                    task_type="discover_companies",
                    payload={"query": "bakeries Berlin", "max_companies": 5},
                    rationale="test retry",
                )
            ],
        )
    )
    assert result.status == "succeeded"
    assert result.retry_count >= 1
    assert attempts["n"] == 2
    assert any(d.decision_type == ManagerDecisionType.RETRY.value for d in result.decisions)


def test_non_retryable_failure(db_session, manager_settings):
    def hard_fail(payload: dict, timeout: float) -> DelegationResult:
        return DelegationResult(
            status="failed",
            summary="validation failed",
            retryable=False,
            error_message="invalid_payload",
        )

    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(research=hard_fail),
        settings=manager_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Generate 5 leads",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="research",
                    task_type="discover_companies",
                    payload={"query": "x"},
                    rationale="fail",
                )
            ],
        )
    )
    assert result.status == "failed"
    assert result.tasks_failed == 1
    assert result.retry_count == 0


def test_cost_limit_stops_run(db_session, manager_settings):
    manager_settings = manager_settings.model_copy(update={"max_ai_cost_per_run": Decimal("0.01")})

    def expensive(payload: dict, timeout: float) -> DelegationResult:
        return DelegationResult(
            status="succeeded",
            summary="expensive research",
            estimated_cost=Decimal("0.05"),
            output={"companies_created": 1},
        )

    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(research=expensive),
        settings=manager_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Generate 20 leads",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="research",
                    task_type="discover_companies",
                    payload={"query": "a"},
                    rationale="cost1",
                ),
                PlannedTaskSpec(
                    agent_name="scoring",
                    task_type="score_companies",
                    payload={"company_ids": []},
                    rationale="cost2",
                ),
            ],
        )
    )
    assert result.status == "stopped"
    assert result.stop_reason == "cost_limit"
    assert any(d.decision_type == ManagerDecisionType.STOP.value for d in result.decisions)


def test_runtime_limit_stops_run(db_session, manager_settings):
    manager_settings = manager_settings.model_copy(update={"max_agent_runtime_seconds": 1})
    clock = {"t": 0.0}

    def fake_clock() -> float:
        return clock["t"]

    def slow(payload: dict, timeout: float) -> DelegationResult:
        clock["t"] += 5.0
        return _ok_research(payload, timeout)

    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(research=slow),
        settings=manager_settings,
        clock=fake_clock,
    )
    result = agent.run(
        ManagerRequest(
            goal="Generate 20 leads",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="research",
                    task_type="discover_companies",
                    payload={"query": "a"},
                    rationale="t1",
                ),
                PlannedTaskSpec(
                    agent_name="scoring",
                    task_type="score_companies",
                    payload={"company_ids": []},
                    rationale="t2",
                ),
            ],
        )
    )
    assert result.status == "stopped"
    assert result.stop_reason == "runtime_limit"


def test_approval_requirement_for_red_action(db_session, manager_settings):
    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(),
        settings=manager_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Transfer money (should not execute)",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="finance",
                    task_type="money_transfer",
                    payload={"amount": 100},
                    rationale="forbidden transfer",
                )
            ],
        )
    )
    assert result.status == "awaiting_approval"
    assert result.stop_reason == "awaiting_approval"
    task = db_session.query(ManagerTask).one()
    assert task.status == ManagerTaskStatus.AWAITING_APPROVAL
    assert task.approval_id is not None
    approval = db_session.get(Approval, task.approval_id)
    assert approval is not None
    assert approval.risk_level == RiskLevel.RED
    assert approval.status == ApprovalStatus.PENDING
    assert any(d.decision_type == ManagerDecisionType.REQUEST_APPROVAL.value for d in result.decisions)
    assert not any("succeeded:money_transfer" in log for log in result.logs)


def test_invalid_task_rejected(db_session, manager_settings):
    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(),
        settings=manager_settings,
    )
    result = agent.run(
        ManagerRequest(
            goal="Do unknown work",
            force_tasks=[
                PlannedTaskSpec(
                    agent_name="unknown_bot",
                    task_type="hack_the_planet",
                    payload={},
                    rationale="invalid",
                )
            ],
        )
    )
    # No ready tasks → all invalid → failed
    assert result.status == "failed"
    task = db_session.query(ManagerTask).one()
    assert task.status == ManagerTaskStatus.INVALID
    assert any(d.decision_type == ManagerDecisionType.REJECT_INVALID.value for d in result.decisions)


def test_duplicate_task_skipped(db_session, manager_settings):
    calls = {"n": 0}

    def count_research(payload: dict, timeout: float) -> DelegationResult:
        calls["n"] += 1
        return _ok_research(payload, timeout)

    same = PlannedTaskSpec(
        agent_name="research",
        task_type="discover_companies",
        payload={"query": "same", "max_companies": 3},
        rationale="dup",
    )
    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(research=count_research),
        settings=manager_settings,
    )
    result = agent.run(ManagerRequest(goal="Generate 3 leads", force_tasks=[same, same]))
    assert result.status == "succeeded"
    assert result.tasks_created == 1
    assert calls["n"] == 1
    assert any(d.decision_type == ManagerDecisionType.SKIP.value for d in result.decisions)
    assert "duplicate_task:discover_companies" in result.logs


def test_evaluate_stop_and_can_retry_helpers():
    snap = LimitSnapshot(
        elapsed_seconds=10,
        estimated_cost=Decimal("1"),
        tasks_created=2,
        retries_used=0,
        max_runtime_seconds=5,
        max_cost=Decimal("5"),
        max_tasks=10,
        max_retries=2,
    )
    assert evaluate_stop(snap).reason == "runtime_limit"
    assert can_retry(attempt_count=1, max_retries=2, retryable=True) is True
    assert can_retry(attempt_count=3, max_retries=2, retryable=True) is False
    assert can_retry(attempt_count=1, max_retries=2, retryable=False) is False


def test_decisions_persisted(db_session, manager_settings):
    agent = ManagerAgent(
        session=db_session,
        executor=_build_executor(),
        settings=manager_settings,
    )
    result = agent.run(ManagerRequest(goal="Generate 10 qualified local business leads."))
    decisions = (
        db_session.query(ManagerDecision)
        .filter(ManagerDecision.manager_run_id == result.manager_run_id)
        .all()
    )
    assert len(decisions) >= 3
    types = {d.decision_type for d in decisions}
    assert ManagerDecisionType.PLAN_CREATED in types
    assert ManagerDecisionType.MEASURE in types
