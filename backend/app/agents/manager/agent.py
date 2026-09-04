"""Manager Agent — central orchestration. Delegates; does not do specialist work.

Core loop: GOAL → PLAN → DELEGATE → EXECUTE → VERIFY → MEASURE → DECIDE → ACT

Enforces task state machine, retries, timeouts, cost/task/runtime limits,
agent permissions, approvals, and decision logging.
Does not send sales outreach, payments, or voice actions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.manager.business_state import inspect_business_state
from app.agents.manager.limits import LimitSnapshot, StopDecision, can_retry, evaluate_stop
from app.agents.manager.permissions import get_permission
from app.agents.manager.planner import create_plan
from app.agents.manager.registry import AgentExecutor
from app.agents.manager.schemas import (
    DecisionSummary,
    DelegationResult,
    ManagerRequest,
    ManagerRunResult,
    PlannedTaskSpec,
    TaskResultSummary,
)
from app.agents.manager.state_machine import InvalidTaskTransition, transition
from app.agents.manager.verification import verify_delegation
from app.approvals.policy import action_type_for_agent
from app.approvals.schemas import ApprovalRequest
from app.approvals.service import ApprovalService
from app.config import Settings
from app.exceptions import ConflictError, ForbiddenError
from app.models import AgentRun, ManagerDecision, ManagerRun, ManagerTask
from app.models.base import utc_now
from app.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    ManagerDecisionType,
    ManagerRunStatus,
    ManagerTaskStatus,
    RiskLevel,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "manager"
TASK_TYPE = "orchestrate_goal"


class ManagerAgent:
    """Orchestrates specialized agents/services toward a high-level goal."""

    def __init__(
        self,
        *,
        session: Session,
        executor: AgentExecutor,
        settings: Settings,
        approval_service: ApprovalService | None = None,
        clock: Any | None = None,
    ) -> None:
        self._session = session
        self._executor = executor
        self._settings = settings
        self._approvals = approval_service or ApprovalService(session, settings)
        self._clock = clock or time.monotonic

    def run(self, request: ManagerRequest) -> ManagerRunResult:
        logs: list[str] = []
        started = self._clock()

        from app.owner.controls import SystemControlService

        try:
            SystemControlService(self._session).assert_ai_operations(actor=AGENT_NAME)
        except ForbiddenError as exc:
            logs.append("system_control:ai_operations_disabled")
            return ManagerRunResult(
                manager_run_id=UUID(int=0),
                agent_run_id=UUID(int=0),
                status="failed",
                goal=request.goal,
                phase="stopped",
                error_message=exc.message,
                logs=logs,
            )

        if request.idempotency_key:
            existing = self._find_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                logs.append("idempotent_replay")
                return self._result_from_run(existing, logs=logs, idempotent_replay=True)

        agent_run = AgentRun(
            agent_name=AGENT_NAME,
            task_type=TASK_TYPE,
            status=AgentRunStatus.RUNNING,
            input_summary=f"goal={request.goal[:200]!r}",
            idempotency_key=request.idempotency_key,
            estimated_cost=Decimal("0"),
            extra_metadata={"goal": request.goal, **(request.metadata or {})},
        )
        manager_run = ManagerRun(
            goal=request.goal,
            status=ManagerRunStatus.PLANNING,
            phase="goal",
            extra_metadata=dict(request.metadata or {}),
        )

        try:
            self._session.add(agent_run)
            self._session.flush()
            manager_run.agent_run_id = agent_run.id
            self._session.add(manager_run)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.exception("Failed to create manager run")
            return ManagerRunResult(
                manager_run_id=UUID(int=0),
                agent_run_id=UUID(int=0),
                status="failed",
                goal=request.goal,
                phase="goal",
                error_message=f"database_failure: {type(exc).__name__}",
                logs=["database_failure_on_run_create"],
            )

        try:
            # GOAL → inspect state
            manager_run.phase = "goal"
            state = inspect_business_state(self._session)
            manager_run.business_state = state.model_dump(mode="json")
            self._record_decision(
                manager_run,
                decision_type=ManagerDecisionType.MEASURE,
                phase="goal",
                action="inspect_business_state",
                rationale="Inspect company memory before planning.",
                inputs={"goal": request.goal},
                outputs=state.model_dump(mode="json"),
            )

            # PLAN
            manager_run.phase = "plan"
            plan = create_plan(request, state, self._settings)
            planned_tasks = list(request.force_tasks) if request.force_tasks is not None else plan.tasks
            if request.force_tasks is not None:
                plan_summary = (
                    f"Forced task list ({len(planned_tasks)} tasks); "
                    f"target_qualified_leads={plan.target_qualified_leads}."
                )
            else:
                plan_summary = plan.summary
            manager_run.target_qualified_leads = plan.target_qualified_leads
            manager_run.plan_summary = plan_summary
            manager_run.measured_qualified_leads = state.qualified_leads
            manager_run.extra_metadata = {
                **(manager_run.extra_metadata or {}),
                "full_cycle": plan.full_cycle,
                "target_mrr": plan.target_mrr,
                "max_monthly_operating_cost": plan.max_monthly_operating_cost,
                "cycle_query": plan.query,
            }
            self._record_decision(
                manager_run,
                decision_type=ManagerDecisionType.PLAN_CREATED,
                phase="plan",
                action="create_plan",
                rationale=plan_summary,
                inputs={
                    "target": plan.target_qualified_leads,
                    "target_mrr": plan.target_mrr,
                    "max_monthly_operating_cost": plan.max_monthly_operating_cost,
                    "full_cycle": plan.full_cycle,
                    "forced": request.force_tasks is not None,
                },
                outputs={
                    "tasks": [t.model_dump() for t in planned_tasks],
                    "query": plan.query,
                },
            )
            logs.append(f"plan_tasks={len(planned_tasks)}")

            created = self._create_tasks(manager_run, planned_tasks, logs=logs)
            manager_run.tasks_created = created
            manager_run.status = ManagerRunStatus.RUNNING
            self._session.flush()

            if created == 0:
                if manager_run.tasks_failed > 0:
                    return self._finalize(
                        manager_run,
                        agent_run,
                        status=ManagerRunStatus.FAILED,
                        stop_reason="all_tasks_invalid",
                        logs=logs + ["all_tasks_invalid"],
                        started=started,
                    )
                return self._finalize(
                    manager_run,
                    agent_run,
                    status=ManagerRunStatus.SUCCEEDED,
                    stop_reason="nothing_to_do",
                    logs=logs,
                    started=started,
                )

            # Main loop: DELEGATE → EXECUTE → VERIFY → MEASURE → DECIDE → ACT
            while True:
                stop = self._check_limits(manager_run, started=started)
                if stop.should_stop:
                    self._record_decision(
                        manager_run,
                        decision_type=ManagerDecisionType.STOP,
                        phase="decide",
                        action="stop",
                        rationale=f"Stop condition: {stop.reason}",
                        inputs=self._limit_inputs(manager_run, started),
                        outputs={"reason": stop.reason},
                    )
                    return self._finalize(
                        manager_run,
                        agent_run,
                        status=ManagerRunStatus.STOPPED,
                        stop_reason=stop.reason,
                        logs=logs + [f"stopped:{stop.reason}"],
                        started=started,
                    )

                task = self._next_ready_task(manager_run.id)
                if task is None:
                    awaiting = self._count_tasks(manager_run.id, ManagerTaskStatus.AWAITING_APPROVAL)
                    if awaiting > 0:
                        return self._finalize(
                            manager_run,
                            agent_run,
                            status=ManagerRunStatus.AWAITING_APPROVAL,
                            stop_reason="awaiting_approval",
                            logs=logs + ["awaiting_approval"],
                            started=started,
                        )
                    # Re-measure and decide if goal met or failed
                    return self._complete_or_fail(manager_run, agent_run, logs=logs, started=started)

                self._process_task(manager_run, task, logs=logs, started=started)
                self._session.flush()

        except Exception as exc:  # noqa: BLE001
            logger.exception("Manager run failed")
            manager_run.status = ManagerRunStatus.FAILED
            manager_run.phase = "failed"
            manager_run.stop_reason = "unhandled_error"
            manager_run.completed_at = utc_now()
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = f"{type(exc).__name__}: {exc}"
            agent_run.completed_at = utc_now()
            self._session.commit()
            return self._result_from_run(manager_run, logs=logs + ["unhandled_error"], error=str(exc))

    def resume(self, manager_run_id: UUID) -> ManagerRunResult:
        """Continue a run after human approval resolution."""
        logs: list[str] = ["resume"]
        started = self._clock()
        manager_run = self._session.get(ManagerRun, manager_run_id)
        if manager_run is None:
            return ManagerRunResult(
                manager_run_id=UUID(int=0),
                agent_run_id=UUID(int=0),
                status="failed",
                goal="",
                phase="failed",
                error_message="manager_run_not_found",
                logs=["manager_run_not_found"],
            )
        agent_run = (
            self._session.get(AgentRun, manager_run.agent_run_id)
            if manager_run.agent_run_id
            else None
        )
        if agent_run is None:
            return ManagerRunResult(
                manager_run_id=manager_run.id,
                agent_run_id=UUID(int=0),
                status="failed",
                goal=manager_run.goal,
                phase="failed",
                error_message="agent_run_not_found",
                logs=["agent_run_not_found"],
            )

        self._sync_approval_tasks(manager_run, logs=logs)
        manager_run.status = ManagerRunStatus.RUNNING
        agent_run.status = AgentRunStatus.RUNNING
        self._session.flush()

        try:
            while True:
                stop = self._check_limits(manager_run, started=started)
                if stop.should_stop:
                    self._record_decision(
                        manager_run,
                        decision_type=ManagerDecisionType.STOP,
                        phase="decide",
                        action="stop",
                        rationale=f"Stop condition: {stop.reason}",
                        inputs=self._limit_inputs(manager_run, started),
                        outputs={"reason": stop.reason},
                    )
                    return self._finalize(
                        manager_run,
                        agent_run,
                        status=ManagerRunStatus.STOPPED,
                        stop_reason=stop.reason,
                        logs=logs + [f"stopped:{stop.reason}"],
                        started=started,
                    )

                task = self._next_ready_task(manager_run.id)
                if task is None:
                    awaiting = self._count_tasks(manager_run.id, ManagerTaskStatus.AWAITING_APPROVAL)
                    if awaiting > 0:
                        return self._finalize(
                            manager_run,
                            agent_run,
                            status=ManagerRunStatus.AWAITING_APPROVAL,
                            stop_reason="awaiting_approval",
                            logs=logs + ["awaiting_approval"],
                            started=started,
                        )
                    return self._complete_or_fail(manager_run, agent_run, logs=logs, started=started)

                self._process_task(manager_run, task, logs=logs, started=started)
                self._session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Manager resume failed")
            manager_run.status = ManagerRunStatus.FAILED
            manager_run.completed_at = utc_now()
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = f"{type(exc).__name__}: {exc}"
            agent_run.completed_at = utc_now()
            self._session.commit()
            return self._result_from_run(manager_run, logs=logs + ["unhandled_error"], error=str(exc))

    def _sync_approval_tasks(self, manager_run: ManagerRun, *, logs: list[str]) -> None:
        """Move awaiting tasks forward or cancel based on approval state."""
        awaiting_tasks = self._session.scalars(
            select(ManagerTask).where(
                ManagerTask.manager_run_id == manager_run.id,
                ManagerTask.status == ManagerTaskStatus.AWAITING_APPROVAL,
            )
        ).all()
        for task in awaiting_tasks:
            if task.approval_id is None:
                continue
            view = self._approvals.get_approval(task.approval_id)
            action_type = action_type_for_agent(task.agent_name, task.task_type)
            if view.status == ApprovalStatus.APPROVED:
                gate = self._approvals.evaluate_gate(action_type, approval_id=task.approval_id)
                if gate.may_execute:
                    self._set_task_status(task, ManagerTaskStatus.READY)
                    logs.append(f"approval_granted:{task.task_type}")
                    self._record_decision(
                        manager_run,
                        decision_type=ManagerDecisionType.ACT,
                        phase="act",
                        action="resume_after_approval",
                        rationale="Human approved YELLOW action; Manager may execute",
                        inputs={"approval_id": str(task.approval_id)},
                        outputs={"status": ManagerTaskStatus.READY.value},
                        task_id=task.id,
                    )
                else:
                    # RED / human-only — approval recorded but agent still cannot execute
                    self._set_task_status(task, ManagerTaskStatus.CANCELLED)
                    task.completed_at = utc_now()
                    task.error_message = "human_only_not_agent_executable"
                    manager_run.tasks_failed += 1
                    logs.append(f"human_only_blocked:{task.task_type}")
            elif view.status in {
                ApprovalStatus.REJECTED,
                ApprovalStatus.EXPIRED,
                ApprovalStatus.CANCELLED,
            }:
                self._set_task_status(task, ManagerTaskStatus.CANCELLED)
                task.completed_at = utc_now()
                task.error_message = f"approval_{view.status.value}"
                manager_run.tasks_failed += 1
                logs.append(f"approval_{view.status.value}:{task.task_type}")
                self._record_decision(
                    manager_run,
                    decision_type=ManagerDecisionType.ACT,
                    phase="act",
                    action="cancel_after_approval_outcome",
                    rationale=f"Approval {view.status.value}",
                    inputs={"approval_id": str(task.approval_id)},
                    outputs={"status": view.status.value},
                    task_id=task.id,
                )

    # --- task processing -------------------------------------------------

    def _process_task(
        self,
        manager_run: ManagerRun,
        task: ManagerTask,
        *,
        logs: list[str],
        started: float,
    ) -> None:
        permission = get_permission(task.agent_name, task.task_type)
        if permission is None:
            self._mark_invalid(manager_run, task, reason="unknown_agent_or_task")
            logs.append(f"invalid:{task.agent_name}/{task.task_type}")
            return

        action_type = permission.action_type
        gate = self._approvals.evaluate_gate(action_type, approval_id=task.approval_id)

        if gate.decision == "require_approval" or (
            gate.decision == "human_only" and task.approval_id is None
        ):
            self._request_approval(
                manager_run,
                task,
                action_type=action_type,
                risk_level=gate.risk_level,
                human_only=gate.decision == "human_only",
            )
            logs.append(f"approval_required:{task.task_type}:{gate.risk_level.value}")
            return

        if gate.decision == "human_only":
            # Approval may exist but agents still cannot execute RED actions
            self._set_task_status(task, ManagerTaskStatus.CANCELLED)
            task.completed_at = utc_now()
            task.error_message = "human_only_not_agent_executable"
            manager_run.tasks_failed += 1
            logs.append(f"human_only_blocked:{task.task_type}")
            return

        if gate.decision == "deny" or not gate.may_execute:
            self._set_task_status(task, ManagerTaskStatus.CANCELLED)
            task.completed_at = utc_now()
            task.error_message = gate.reason
            manager_run.tasks_failed += 1
            logs.append(f"gate_deny:{task.task_type}")
            return

        # Bypass protection — hard assert before any delegation
        try:
            self._approvals.assert_executable(action_type, approval_id=task.approval_id)
        except ForbiddenError as exc:
            self._set_task_status(task, ManagerTaskStatus.CANCELLED)
            task.completed_at = utc_now()
            task.error_message = exc.message
            manager_run.tasks_failed += 1
            logs.append(f"bypass_blocked:{task.task_type}")
            return

        # DELEGATE decision
        manager_run.phase = "delegate"
        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.DELEGATE,
            phase="delegate",
            action=f"delegate:{task.agent_name}/{task.task_type}",
            rationale=f"Delegate to {task.agent_name} ({permission.description})",
            inputs={"payload": task.payload, "approval_id": str(task.approval_id) if task.approval_id else None},
            outputs={"task_id": str(task.id)},
            task_id=task.id,
        )

        # EXECUTE
        manager_run.phase = "execute"
        self._set_task_status(task, ManagerTaskStatus.RUNNING)
        task.started_at = utc_now()
        task.attempt_count += 1
        self._session.flush()

        remaining = max(
            1.0,
            float(self._settings.max_agent_runtime_seconds) - (self._clock() - started),
        )
        per_task_timeout = min(remaining, float(self._settings.max_agent_runtime_seconds))

        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.EXECUTE,
            phase="execute",
            action="execute_task",
            rationale=f"Execute attempt={task.attempt_count}",
            inputs={"timeout_seconds": per_task_timeout},
            outputs={},
            task_id=task.id,
        )

        result = self._executor.execute(
            agent_name=task.agent_name,
            task_type=task.task_type,
            payload=dict(task.payload or {}),
            timeout_seconds=per_task_timeout,
        )

        cost = result.estimated_cost or Decimal("0")
        task.estimated_cost = (task.estimated_cost or Decimal("0")) + cost
        manager_run.estimated_cost = (manager_run.estimated_cost or Decimal("0")) + cost
        task.result_summary = result.summary[:2000]
        task.result_payload = result.output
        if result.error_message:
            task.error_message = result.error_message[:2000]

        # VERIFY
        manager_run.phase = "verify"
        verification = verify_delegation(
            agent_name=task.agent_name,
            task_type=task.task_type,
            result=result,
        )
        task.verified = verification.ok
        task.verification_notes = verification.notes
        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.VERIFY,
            phase="verify",
            action="verify_result",
            rationale=verification.notes,
            inputs={"status": result.status},
            outputs={"ok": verification.ok},
            task_id=task.id,
        )

        # MEASURE
        manager_run.phase = "measure"
        state = inspect_business_state(self._session)
        manager_run.business_state = state.model_dump(mode="json")
        manager_run.measured_qualified_leads = state.qualified_leads
        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.MEASURE,
            phase="measure",
            action="measure_progress",
            rationale=(
                f"qualified={state.qualified_leads}/"
                f"{manager_run.target_qualified_leads}"
            ),
            inputs={},
            outputs=state.model_dump(mode="json"),
            task_id=task.id,
        )

        # DECIDE + ACT
        manager_run.phase = "decide"
        if result.status == "timeout" or (
            result.status in {"failed", "partial"} and not verification.ok
        ):
            self._handle_failure(manager_run, task, result, logs=logs)
            return

        if result.status in {"succeeded", "partial"} and verification.ok:
            self._set_task_status(task, ManagerTaskStatus.SUCCEEDED)
            task.completed_at = utc_now()
            manager_run.tasks_succeeded += 1
            self._record_decision(
                manager_run,
                decision_type=ManagerDecisionType.ACT,
                phase="act",
                action="accept_result",
                rationale="Verified successful delegation.",
                inputs={},
                outputs={"summary": result.summary},
                task_id=task.id,
            )
            logs.append(f"succeeded:{task.task_type}")
            return

        # Unverified success → treat as retryable failure
        self._handle_failure(
            manager_run,
            task,
            DelegationResult(
                status="failed",
                summary=result.summary,
                estimated_cost=Decimal("0"),
                output=result.output,
                retryable=True,
                error_message=f"verification_failed:{verification.notes}",
            ),
            logs=logs,
        )

    def _request_approval(
        self,
        manager_run: ManagerRun,
        task: ManagerTask,
        *,
        action_type: str,
        risk_level: RiskLevel,
        human_only: bool,
    ) -> None:
        if task.approval_id is not None:
            self._set_task_status(task, ManagerTaskStatus.AWAITING_APPROVAL)
            return

        req = ApprovalRequest(
            action_type=action_type,
            description=(
                f"Manager requests approval for {task.agent_name}/{task.task_type}. "
                f"{'Human-only (RED); agents will not execute.' if human_only else ''}"
            ).strip(),
            requested_by=AGENT_NAME,
            action_payload=dict(task.payload or {}),
            risk_level=risk_level,
            manager_run_id=manager_run.id,
            manager_task_id=task.id,
            agent_run_id=manager_run.agent_run_id,
            metadata={"human_only": human_only},
        )
        try:
            view = self._approvals.request_approval(req)
            approval_id = view.id
        except ConflictError as exc:
            approval_id = UUID(str(exc.details["approval_id"]))

        task.approval_id = approval_id
        if task.status == ManagerTaskStatus.READY:
            self._set_task_status(task, ManagerTaskStatus.AWAITING_APPROVAL)
        elif task.status == ManagerTaskStatus.PENDING:
            self._set_task_status(task, ManagerTaskStatus.READY)
            self._set_task_status(task, ManagerTaskStatus.AWAITING_APPROVAL)
        else:
            try:
                self._set_task_status(task, ManagerTaskStatus.AWAITING_APPROVAL)
            except InvalidTaskTransition:
                if task.status != ManagerTaskStatus.AWAITING_APPROVAL:
                    raise

        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.REQUEST_APPROVAL,
            phase="delegate",
            action="request_approval",
            rationale=f"Risk={risk_level.value}; human_only={human_only}",
            inputs={"task_type": task.task_type, "action_type": action_type},
            outputs={"approval_id": str(approval_id)},
            task_id=task.id,
        )

    def _handle_failure(
        self,
        manager_run: ManagerRun,
        task: ManagerTask,
        result: DelegationResult,
        *,
        logs: list[str],
    ) -> None:
        terminal_status = (
            ManagerTaskStatus.TIMED_OUT
            if result.status == "timeout"
            else ManagerTaskStatus.FAILED
        )
        self._set_task_status(task, terminal_status)
        retryable = result.retryable or result.status == "timeout"
        if can_retry(
            attempt_count=task.attempt_count,
            max_retries=task.max_retries,
            retryable=retryable,
        ):
            self._set_task_status(task, ManagerTaskStatus.RETRYING)
            self._set_task_status(task, ManagerTaskStatus.READY)
            manager_run.retry_count += 1
            self._record_decision(
                manager_run,
                decision_type=ManagerDecisionType.RETRY,
                phase="decide",
                action="retry_task",
                rationale=f"Safe failure retry attempt_count={task.attempt_count}",
                inputs={"error": result.error_message},
                outputs={"next_status": ManagerTaskStatus.READY.value},
                task_id=task.id,
            )
            logs.append(f"retry:{task.task_type}:{task.attempt_count}")
            return

        task.completed_at = utc_now()
        manager_run.tasks_failed += 1
        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.ACT,
            phase="act",
            action="accept_failure",
            rationale="Retries exhausted or non-retryable failure.",
            inputs={"error": result.error_message},
            outputs={"status": terminal_status.value},
            task_id=task.id,
        )
        logs.append(f"failed_final:{task.task_type}")

    def _mark_invalid(self, manager_run: ManagerRun, task: ManagerTask, *, reason: str) -> None:
        self._set_task_status(task, ManagerTaskStatus.INVALID)
        task.error_message = reason
        task.completed_at = utc_now()
        manager_run.tasks_failed += 1
        self._record_decision(
            manager_run,
            decision_type=ManagerDecisionType.REJECT_INVALID,
            phase="delegate",
            action="reject_invalid_task",
            rationale=reason,
            inputs={"agent": task.agent_name, "task_type": task.task_type},
            outputs={},
            task_id=task.id,
        )

    # --- task creation ---------------------------------------------------

    def _create_tasks(
        self,
        manager_run: ManagerRun,
        specs: list[PlannedTaskSpec],
        *,
        logs: list[str],
    ) -> int:
        created = 0
        max_tasks = self._settings.max_tasks_per_run
        seen_fingerprints = set(
            self._session.scalars(
                select(ManagerTask.fingerprint).where(
                    ManagerTask.manager_run_id == manager_run.id
                )
            ).all()
        )
        for index, spec in enumerate(specs):
            if created >= max_tasks:
                logs.append("task_limit_on_create")
                self._record_decision(
                    manager_run,
                    decision_type=ManagerDecisionType.STOP,
                    phase="plan",
                    action="cap_tasks",
                    rationale="max_tasks_per_run reached while creating plan tasks",
                    inputs={"max_tasks": max_tasks},
                    outputs={"created": created},
                )
                break

            permission = get_permission(spec.agent_name, spec.task_type)
            fingerprint = self._fingerprint(spec)
            if fingerprint in seen_fingerprints:
                logs.append(f"duplicate_task:{spec.task_type}")
                self._record_decision(
                    manager_run,
                    decision_type=ManagerDecisionType.SKIP,
                    phase="plan",
                    action="skip_duplicate_task",
                    rationale="Duplicate fingerprint within run",
                    inputs=spec.model_dump(),
                    outputs={"fingerprint": fingerprint},
                )
                continue

            task = ManagerTask(
                manager_run_id=manager_run.id,
                sequence=index,
                agent_name=spec.agent_name.lower(),
                task_type=spec.task_type.lower(),
                status=ManagerTaskStatus.PENDING,
                risk_level=permission.risk_level if permission else RiskLevel.RED,
                fingerprint=fingerprint,
                payload=spec.payload,
                max_retries=self._settings.max_retries,
                extra_metadata={"rationale": spec.rationale},
            )
            self._session.add(task)
            self._session.flush()
            seen_fingerprints.add(fingerprint)

            if permission is None:
                self._set_task_status(task, ManagerTaskStatus.INVALID)
                task.error_message = "unknown_agent_or_task"
                task.completed_at = utc_now()
                manager_run.tasks_failed += 1
                self._record_decision(
                    manager_run,
                    decision_type=ManagerDecisionType.REJECT_INVALID,
                    phase="plan",
                    action="reject_invalid_task",
                    rationale="Unknown agent/task not in permission allow-list",
                    inputs=spec.model_dump(),
                    outputs={},
                    task_id=task.id,
                )
            else:
                self._set_task_status(task, ManagerTaskStatus.READY)
                created += 1
        return created

    @staticmethod
    def _fingerprint(spec: PlannedTaskSpec) -> str:
        payload = json.dumps(spec.payload, sort_keys=True, default=str)
        raw = f"{spec.agent_name.lower()}|{spec.task_type.lower()}|{payload}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    # --- completion ------------------------------------------------------

    def _complete_or_fail(
        self,
        manager_run: ManagerRun,
        agent_run: AgentRun,
        *,
        logs: list[str],
        started: float,
    ) -> ManagerRunResult:
        from decimal import Decimal as Dec

        from app.agents.manager.cycle import CycleGoal, evaluate_goal_met

        state = inspect_business_state(self._session)
        manager_run.measured_qualified_leads = state.qualified_leads
        manager_run.business_state = state.model_dump(mode="json")
        meta = manager_run.extra_metadata or {}
        target = manager_run.target_qualified_leads or 0
        target_mrr = meta.get("target_mrr")
        cost_cap = meta.get("max_monthly_operating_cost")
        cycle_goal = CycleGoal(
            target_qualified_leads=target or 0,
            target_mrr=Dec(target_mrr) if target_mrr not in (None, "") else None,
            max_monthly_operating_cost=Dec(cost_cap) if cost_cap not in (None, "") else None,
            full_cycle=bool(meta.get("full_cycle")),
            currency_hint="UNKNOWN",
        )
        met, rationale = evaluate_goal_met(cycle_goal, state)
        if met and (target or cycle_goal.target_mrr is not None or cycle_goal.max_monthly_operating_cost is not None):
            self._record_decision(
                manager_run,
                decision_type=ManagerDecisionType.COMPLETE,
                phase="decide",
                action="goal_met",
                rationale=rationale,
                inputs={"target": target, "target_mrr": target_mrr},
                outputs=state.model_dump(mode="json"),
            )
            return self._finalize(
                manager_run,
                agent_run,
                status=ManagerRunStatus.SUCCEEDED,
                stop_reason="goal_met",
                logs=logs + ["goal_met", rationale],
                started=started,
            )

        if manager_run.tasks_succeeded > 0 and manager_run.tasks_failed == 0:
            self._record_decision(
                manager_run,
                decision_type=ManagerDecisionType.COMPLETE,
                phase="decide",
                action="plan_complete",
                rationale="All planned tasks succeeded; goal may still be in progress.",
                inputs={"qualified": state.qualified_leads, "target": target, "mrr": str(state.mrr)},
                outputs={},
            )
            return self._finalize(
                manager_run,
                agent_run,
                status=ManagerRunStatus.SUCCEEDED,
                stop_reason="plan_complete",
                logs=logs + ["plan_complete"],
                started=started,
            )

        if manager_run.tasks_succeeded > 0:
            return self._finalize(
                manager_run,
                agent_run,
                status=ManagerRunStatus.SUCCEEDED,
                stop_reason="partial_progress",
                logs=logs + ["partial_progress"],
                started=started,
            )

        return self._finalize(
            manager_run,
            agent_run,
            status=ManagerRunStatus.FAILED,
            stop_reason="all_tasks_failed",
            logs=logs + ["all_tasks_failed"],
            started=started,
        )

    def _finalize(
        self,
        manager_run: ManagerRun,
        agent_run: AgentRun,
        *,
        status: ManagerRunStatus,
        stop_reason: str | None,
        logs: list[str],
        started: float,
    ) -> ManagerRunResult:
        manager_run.status = status
        manager_run.stop_reason = stop_reason
        manager_run.completed_at = utc_now()
        manager_run.phase = "act" if status != ManagerRunStatus.FAILED else "failed"
        agent_run.estimated_cost = manager_run.estimated_cost or Decimal("0")
        agent_run.completed_at = utc_now()
        agent_run.output_summary = (
            f"status={status.value} stop={stop_reason} "
            f"tasks_ok={manager_run.tasks_succeeded} failed={manager_run.tasks_failed}"
        )
        if status == ManagerRunStatus.SUCCEEDED:
            agent_run.status = AgentRunStatus.SUCCEEDED
        elif status == ManagerRunStatus.AWAITING_APPROVAL:
            agent_run.status = AgentRunStatus.AWAITING_APPROVAL
        elif status == ManagerRunStatus.STOPPED:
            agent_run.status = AgentRunStatus.CANCELLED
            agent_run.error_message = stop_reason
        else:
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = stop_reason
        elapsed = self._clock() - started
        manager_run.extra_metadata = {
            **(manager_run.extra_metadata or {}),
            "elapsed_seconds": elapsed,
            "logs": logs[-50:],
        }
        self._session.commit()
        return self._result_from_run(manager_run, logs=logs)

    # --- helpers ---------------------------------------------------------

    def _check_limits(self, manager_run: ManagerRun, *, started: float):
        from app.pilot.execution import ExecutionGuard
        from app.security import daily_cost_total

        daily_spend = daily_cost_total(self._session)
        decision = evaluate_stop(
            LimitSnapshot(
                elapsed_seconds=self._clock() - started,
                estimated_cost=manager_run.estimated_cost or Decimal("0"),
                tasks_created=manager_run.tasks_created,
                retries_used=manager_run.retry_count,
                max_runtime_seconds=self._settings.max_agent_runtime_seconds,
                max_cost=self._settings.max_ai_cost_per_run,
                max_tasks=self._settings.max_tasks_per_run,
                max_retries=self._settings.max_retries,
                daily_spend=daily_spend,
                daily_budget_limit=self._settings.daily_budget_limit,
            )
        )
        if decision.should_stop:
            return decision

        # Pilot Mode operational caps — stop safely before another task starts.
        guard = ExecutionGuard(self._session, self._settings)
        blocked = guard.limits.any_daily_limit_reached()
        if blocked is not None:
            return StopDecision(True, blocked.reason or "pilot_daily_limit")
        budget = guard.budget.status()
        if budget.exhausted:
            return StopDecision(True, "daily_budget_limit")
        return decision

    def _limit_inputs(self, manager_run: ManagerRun, started: float) -> dict[str, Any]:
        return {
            "elapsed_seconds": self._clock() - started,
            "estimated_cost": str(manager_run.estimated_cost or Decimal("0")),
            "tasks_created": manager_run.tasks_created,
            "retry_count": manager_run.retry_count,
        }

    def _set_task_status(self, task: ManagerTask, target: ManagerTaskStatus) -> None:
        try:
            task.status = transition(task.status, target)
        except InvalidTaskTransition:
            logger.exception(
                "Invalid task transition task_id=%s from=%s to=%s",
                task.id,
                task.status,
                target,
            )
            raise

    def _next_ready_task(self, manager_run_id: UUID) -> ManagerTask | None:
        return self._session.scalar(
            select(ManagerTask)
            .where(
                ManagerTask.manager_run_id == manager_run_id,
                ManagerTask.status == ManagerTaskStatus.READY,
            )
            .order_by(ManagerTask.sequence.asc(), ManagerTask.created_at.asc())
            .limit(1)
        )

    def _count_tasks(self, manager_run_id: UUID, status: ManagerTaskStatus) -> int:
        from sqlalchemy import func

        return int(
            self._session.scalar(
                select(func.count())
                .select_from(ManagerTask)
                .where(
                    ManagerTask.manager_run_id == manager_run_id,
                    ManagerTask.status == status,
                )
            )
            or 0
        )

    def _record_decision(
        self,
        manager_run: ManagerRun,
        *,
        decision_type: ManagerDecisionType,
        phase: str,
        action: str,
        rationale: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        task_id: UUID | None = None,
    ) -> None:
        decision = ManagerDecision(
            manager_run_id=manager_run.id,
            task_id=task_id,
            decision_type=decision_type,
            phase=phase,
            action=action[:128],
            rationale=rationale[:4000],
            inputs=inputs,
            outputs=outputs,
        )
        self._session.add(decision)

    def _find_by_idempotency_key(self, key: str) -> ManagerRun | None:
        agent_run = self._session.scalar(
            select(AgentRun).where(
                AgentRun.idempotency_key == key,
                AgentRun.agent_name == AGENT_NAME,
            )
        )
        if agent_run is None:
            return None
        return self._session.scalar(
            select(ManagerRun).where(ManagerRun.agent_run_id == agent_run.id)
        )

    def _result_from_run(
        self,
        manager_run: ManagerRun,
        *,
        logs: list[str],
        idempotent_replay: bool = False,
        error: str | None = None,
    ) -> ManagerRunResult:
        self._session.refresh(manager_run)
        tasks = list(
            self._session.scalars(
                select(ManagerTask)
                .where(ManagerTask.manager_run_id == manager_run.id)
                .order_by(ManagerTask.sequence.asc())
            )
        )
        decisions = list(
            self._session.scalars(
                select(ManagerDecision)
                .where(ManagerDecision.manager_run_id == manager_run.id)
                .order_by(ManagerDecision.created_at.asc())
            )
        )
        status_map = {
            ManagerRunStatus.SUCCEEDED: "succeeded",
            ManagerRunStatus.FAILED: "failed",
            ManagerRunStatus.STOPPED: "stopped",
            ManagerRunStatus.AWAITING_APPROVAL: "awaiting_approval",
            ManagerRunStatus.CANCELLED: "cancelled",
        }
        return ManagerRunResult(
            manager_run_id=manager_run.id,
            agent_run_id=manager_run.agent_run_id or UUID(int=0),
            status=status_map.get(manager_run.status, "failed"),  # type: ignore[arg-type]
            goal=manager_run.goal,
            phase=manager_run.phase,
            plan_summary=manager_run.plan_summary,
            stop_reason=manager_run.stop_reason,
            target_qualified_leads=manager_run.target_qualified_leads,
            measured_qualified_leads=manager_run.measured_qualified_leads,
            tasks_created=manager_run.tasks_created,
            tasks_succeeded=manager_run.tasks_succeeded,
            tasks_failed=manager_run.tasks_failed,
            retry_count=manager_run.retry_count,
            estimated_cost=manager_run.estimated_cost or Decimal("0"),
            tasks=[
                TaskResultSummary(
                    task_id=t.id,
                    agent_name=t.agent_name,
                    task_type=t.task_type,
                    status=t.status.value if hasattr(t.status, "value") else str(t.status),
                    verified=bool(t.verified),
                    attempt_count=t.attempt_count,
                    estimated_cost=t.estimated_cost or Decimal("0"),
                    summary=t.result_summary,
                    error_message=t.error_message,
                )
                for t in tasks
            ],
            decisions=[
                DecisionSummary(
                    decision_type=d.decision_type.value
                    if hasattr(d.decision_type, "value")
                    else str(d.decision_type),
                    phase=d.phase,
                    action=d.action,
                    rationale=d.rationale,
                )
                for d in decisions
            ],
            business_state=manager_run.business_state or {},
            idempotent_replay=idempotent_replay,
            error_message=error or None,
            logs=logs,
        )
