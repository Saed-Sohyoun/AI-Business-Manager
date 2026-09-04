"""Owner command service — FIND_OPPORTUNITIES and related governed launches."""

from __future__ import annotations

import logging
import threading
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.manager.agent import ManagerAgent
from app.agents.manager.schemas import ManagerRequest, PlannedTaskSpec
from app.config import Settings
from app.database import get_session_factory
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.base import utc_now
from app.models.owner_execution import OwnerExecution
from app.models.owner_execution_enums import (
    OwnerCommandType,
    OwnerExecutionState,
    can_transition,
)
from app.orchestration.handlers import build_manager_executor
from app.owner.controls import SystemControlService
from app.owner.schemas_commands import (
    ExecutionView,
    FindOpportunitiesRequest,
    FindOpportunitiesResponse,
)
from app.pilot.limits import LimitService
from app.security.events import record_security_event
from app.security.redaction import redact_dict

logger = logging.getLogger(__name__)


class OwnerCommandService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def find_opportunities(
        self,
        request: FindOpportunitiesRequest,
        *,
        owner_id: str,
        correlation_id: str | None = None,
    ) -> FindOpportunitiesResponse:
        controls = SystemControlService(self._session)
        try:
            controls.assert_ai_operations(actor=owner_id)
        except ForbiddenError as exc:
            raise ForbiddenError(
                "AI operations are paused — cannot start opportunity search.",
                details={"code": "SYSTEM_PAUSED", **(exc.details or {})},
            ) from exc

        limits = LimitService(self._session, self._settings)
        remaining = limits.remaining_companies_capacity()
        desired = min(request.desired_count, remaining, self._settings.max_companies_per_day)
        if desired <= 0:
            raise ForbiddenError(
                "Daily company research limit reached.",
                details={"code": "LIMIT_REACHED"},
            )

        existing = self._session.scalar(
            select(OwnerExecution).where(
                OwnerExecution.command_type == OwnerCommandType.FIND_OPPORTUNITIES.value,
                OwnerExecution.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            return FindOpportunitiesResponse(
                execution_id=existing.id,
                status=existing.status,
                message=existing.result_summary
                or "Your team is already working on this request.",
            )

        niche = (request.niche or "local businesses").strip()
        location = (request.location or "Berlin").strip()
        query = f"{niche} {location} website".strip()

        execution = OwnerExecution(
            command_type=OwnerCommandType.FIND_OPPORTUNITIES.value,
            title="Finding opportunities",
            purpose=f"Discover and qualify {desired} businesses in {location} ({niche})",
            status=OwnerExecutionState.QUEUED.value,
            idempotency_key=request.idempotency_key,
            requested_by=owner_id,
            progress=0,
            completed_steps=0,
            total_steps=4,
            current_activity="Starting",
            request_payload=redact_dict(
                {
                    "niche": niche,
                    "location": location,
                    "desired_count": desired,
                    "query": query,
                }
            ),
            correlation_id=correlation_id,
            started_at=utc_now(),
        )
        try:
            with self._session.begin_nested():
                self._session.add(execution)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(OwnerExecution).where(
                    OwnerExecution.command_type == OwnerCommandType.FIND_OPPORTUNITIES.value,
                    OwnerExecution.idempotency_key == request.idempotency_key,
                )
            )
            if existing is None:
                raise
            return FindOpportunitiesResponse(
                execution_id=existing.id,
                status=existing.status,
                message="Your team is already working on this request.",
            )

        self._session.commit()
        execution_id = execution.id
        self._spawn_find_opportunities(execution_id, query=query, location=location, niche=niche, max_companies=desired)

        return FindOpportunitiesResponse(
            execution_id=execution_id,
            status=OwnerExecutionState.QUEUED.value,
            message="Your team has started looking for opportunities.",
        )

    def get_execution(self, execution_id: UUID) -> ExecutionView:
        row = self._session.get(OwnerExecution, execution_id)
        if row is None:
            raise NotFoundError("Execution not found", details={"execution_id": str(execution_id)})
        return self._to_view(row)

    def list_executions(self, *, limit: int = 50) -> list[ExecutionView]:
        capped = max(1, min(limit, 100))
        rows = self._session.scalars(
            select(OwnerExecution).order_by(OwnerExecution.started_at.desc()).limit(capped)
        ).all()
        return [self._to_view(r) for r in rows]

    def cancel(self, execution_id: UUID, *, owner_id: str) -> ExecutionView:
        row = self._session.get(OwnerExecution, execution_id)
        if row is None:
            raise NotFoundError("Execution not found", details={"execution_id": str(execution_id)})
        if not can_transition(row.status, OwnerExecutionState.CANCELLED):
            if row.status in {
                OwnerExecutionState.COMPLETED.value,
                OwnerExecutionState.CANCELLED.value,
                OwnerExecutionState.FAILED.value,
            }:
                return self._to_view(row)
            raise ConflictError(
                "Cannot cancel execution in its current state",
                details={"code": "STATE_TRANSITION_INVALID", "status": row.status},
            )
        row.cancel_requested = True
        row.status = OwnerExecutionState.CANCELLED.value
        row.completed_at = utc_now()
        row.current_activity = "Cancelled"
        row.result_summary = "Cancelled by owner. Committed results were kept."
        record_security_event(
            self._session,
            event_type="OWNER_EXECUTION_CANCELLED",
            reason="owner_cancel",
            details={"actor": owner_id, "execution_id": str(execution_id)},
        )
        self._session.commit()
        return self._to_view(row)

    def _spawn_find_opportunities(
        self,
        execution_id: UUID,
        *,
        query: str,
        location: str,
        niche: str,
        max_companies: int,
    ) -> None:
        settings = self._settings

        def runner() -> None:
            session = get_session_factory()()
            try:
                row = session.get(OwnerExecution, execution_id)
                if row is None or row.cancel_requested:
                    return
                if not can_transition(row.status, OwnerExecutionState.RUNNING):
                    return
                row.status = OwnerExecutionState.RUNNING.value
                row.current_activity = "Researching"
                row.progress = 10
                session.commit()

                try:
                    SystemControlService(session).assert_ai_operations(actor="owner_command")
                except ForbiddenError as exc:
                    row = session.get(OwnerExecution, execution_id)
                    if row:
                        row.status = OwnerExecutionState.BLOCKED.value
                        row.failure_message = exc.message
                        row.completed_at = utc_now()
                        session.commit()
                    return

                executor = build_manager_executor(session, settings)
                manager = ManagerAgent(session=session, executor=executor, settings=settings)
                result = manager.run(
                    ManagerRequest(
                        goal=f"Find and qualify opportunities: {niche} in {location}",
                        industry=niche,
                        location=location,
                        query=query,
                        force_tasks=[
                            PlannedTaskSpec(
                                agent_name="research",
                                task_type="discover_companies",
                                payload={
                                    "query": query,
                                    "industry": niche,
                                    "location": location,
                                    "max_companies": max_companies,
                                    "verify_with_browser": True,
                                },
                                rationale="Owner requested opportunity discovery",
                            )
                        ],
                        idempotency_key=f"owner-exec-{execution_id}",
                        metadata={"owner_execution_id": str(execution_id)},
                    )
                )

                row = session.get(OwnerExecution, execution_id)
                if row is None:
                    return
                if row.cancel_requested:
                    row.status = OwnerExecutionState.CANCELLED.value
                    row.completed_at = utc_now()
                    session.commit()
                    return

                row.manager_run_id = result.manager_run_id
                row.agent_run_id = result.agent_run_id
                row.completed_steps = 4
                row.total_steps = 4
                row.progress = 100
                if result.status in {"succeeded", "awaiting_approval"}:
                    row.status = (
                        OwnerExecutionState.WAITING_FOR_APPROVAL.value
                        if result.status == "awaiting_approval"
                        else OwnerExecutionState.COMPLETED.value
                    )
                    row.current_activity = "Completed"
                    row.result_summary = (
                        result.plan_summary
                        or f"Research finished with status={result.status}."
                    )
                elif result.status == "stopped":
                    row.status = OwnerExecutionState.PARTIALLY_COMPLETED.value
                    row.current_activity = "Stopped"
                    row.result_summary = result.stop_reason or "Stopped with partial results."
                else:
                    row.status = OwnerExecutionState.FAILED.value
                    row.current_activity = "Failed"
                    row.failure_message = result.error_message or "Opportunity search failed."
                row.completed_at = utc_now()
                session.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("owner_find_opportunities_failed id=%s", execution_id)
                try:
                    row = session.get(OwnerExecution, execution_id)
                    if row is not None:
                        row.status = OwnerExecutionState.FAILED.value
                        row.failure_message = str(exc)[:2000]
                        row.completed_at = utc_now()
                        session.commit()
                except Exception:  # noqa: BLE001
                    session.rollback()
            finally:
                session.close()

        threading.Thread(target=runner, name=f"owner-exec-{execution_id}", daemon=True).start()

    def _to_view(self, row: OwnerExecution) -> ExecutionView:
        return ExecutionView(
            id=row.id,
            title=row.title,
            purpose=row.purpose,
            state=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            progress=row.progress,
            completed_steps=row.completed_steps,
            total_steps=row.total_steps,
            current_activity=row.current_activity,
            result_summary=row.result_summary,
            needs_attention=bool(row.needs_attention),
            failure_message=row.failure_message,
            command_type=row.command_type,
            advanced_details={
                "execution_id": str(row.id),
                "manager_run_id": str(row.manager_run_id) if row.manager_run_id else None,
                "agent_run_id": str(row.agent_run_id) if row.agent_run_id else None,
                "correlation_id": row.correlation_id,
            },
        )
