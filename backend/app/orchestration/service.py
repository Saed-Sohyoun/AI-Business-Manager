"""N8nOrchestrationService — execution tracking, idempotency, timeouts, retries.

n8n only triggers. Handlers invoke backend agents/services. Approvals are never bypassed.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import ConflictError, NotFoundError, ValidationAppError, WorkflowTimeoutError
from app.models import WorkflowExecution
from app.models.base import utc_now
from app.models.enums import WorkflowExecutionStatus, WorkflowName
from app.orchestration.handlers import build_default_handlers
from app.orchestration.schemas import WorkflowExecutionView, WorkflowTriggerRequest

logger = logging.getLogger(__name__)

WorkflowHandler = Callable[[dict[str, Any], float], dict[str, Any]]

_TERMINAL_SUCCESS = {WorkflowExecutionStatus.SUCCEEDED}
_RETRYABLE = {WorkflowExecutionStatus.FAILED, WorkflowExecutionStatus.TIMED_OUT}
# Extra grace after timeout before a RUNNING row is treated as abandoned.
_STALE_RUNNING_GRACE_SECONDS = 30.0


def _as_status(value: WorkflowExecutionStatus | str) -> WorkflowExecutionStatus:
    return value if isinstance(value, WorkflowExecutionStatus) else WorkflowExecutionStatus(value)


def _as_name(value: WorkflowName | str) -> WorkflowName:
    return value if isinstance(value, WorkflowName) else WorkflowName(value)


class N8nOrchestrationService:
    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        handlers: dict[str, WorkflowHandler] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._handlers = handlers if handlers is not None else build_default_handlers(session, settings)

    def trigger(
        self,
        workflow_name: WorkflowName | str,
        request: WorkflowTriggerRequest,
    ) -> WorkflowExecutionView:
        name = _as_name(workflow_name)
        if name.value not in self._handlers:
            raise ValidationAppError(
                f"Unknown workflow: {name.value}",
                details={"workflow_name": name.value},
            )

        timeout = float(
            request.timeout_seconds
            if request.timeout_seconds is not None
            else self._settings.n8n_default_timeout_seconds
        )
        existing = self._find(name, request.idempotency_key)
        if existing is not None:
            return self._handle_existing(existing, request=request, timeout=timeout)

        execution = WorkflowExecution(
            workflow_name=name,
            idempotency_key=request.idempotency_key,
            status=WorkflowExecutionStatus.RECEIVED,
            trigger_source="n8n",
            attempt=1,
            timeout_seconds=timeout,
            started_at=utc_now(),
            request_payload=dict(request.payload or {}),
            result_summary={},
            correlation_id=request.correlation_id,
            extra_metadata=dict(request.metadata or {}),
        )
        try:
            with self._session.begin_nested():
                self._session.add(execution)
                self._session.flush()
        except IntegrityError:
            # Concurrent insert with the same idempotency key — replay safely.
            existing = self._find(name, request.idempotency_key)
            if existing is None:
                raise
            return self._handle_existing(existing, request=request, timeout=timeout)

        return self._run(execution)

    def get_execution(self, execution_id: UUID) -> WorkflowExecutionView:
        row = self._session.get(WorkflowExecution, execution_id)
        if row is None:
            raise NotFoundError(
                "Workflow execution not found",
                details={"execution_id": str(execution_id)},
            )
        return self._to_view(row)

    def list_executions(
        self,
        *,
        workflow_name: WorkflowName | str | None = None,
        limit: int = 50,
    ) -> list[WorkflowExecutionView]:
        capped = max(1, min(limit, 200))
        stmt = select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc()).limit(capped)
        if workflow_name is not None:
            stmt = stmt.where(WorkflowExecution.workflow_name == _as_name(workflow_name).value)
        rows = self._session.scalars(stmt).all()
        return [self._to_view(row) for row in rows]

    def _is_stale_running(self, existing: WorkflowExecution) -> bool:
        timeout = float(existing.timeout_seconds or self._settings.n8n_default_timeout_seconds)
        started = existing.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        deadline = started + timedelta(seconds=timeout + _STALE_RUNNING_GRACE_SECONDS)
        return utc_now() > deadline

    def _handle_existing(
        self,
        existing: WorkflowExecution,
        *,
        request: WorkflowTriggerRequest,
        timeout: float,
    ) -> WorkflowExecutionView:
        status = _as_status(existing.status)
        if status == WorkflowExecutionStatus.RUNNING:
            if not self._is_stale_running(existing):
                raise ConflictError(
                    "Workflow execution already running",
                    details={
                        "execution_id": str(existing.id),
                        "workflow_name": str(existing.workflow_name),
                        "idempotency_key": existing.idempotency_key,
                    },
                )
            # Abandoned worker / crash after commit to RUNNING — reclaim as timed out.
            existing.status = WorkflowExecutionStatus.TIMED_OUT
            existing.error_message = "Stale RUNNING execution reclaimed after timeout"
            existing.finished_at = utc_now()
            existing.result_summary = {
                "error": "stale_running_reclaimed",
                "details": {"grace_seconds": _STALE_RUNNING_GRACE_SECONDS},
            }
            self._session.flush()
            status = WorkflowExecutionStatus.TIMED_OUT

        if status in _TERMINAL_SUCCESS:
            return self._to_view(existing, idempotent_replay=True)

        if status in _RETRYABLE:
            max_retries = self._settings.n8n_max_execution_retries
            # attempt starts at 1; retries allowed while attempt <= max_retries + 1 total tries
            if existing.attempt > max_retries:
                return self._to_view(existing, idempotent_replay=True, retryable=False)
            existing.attempt += 1
            existing.timeout_seconds = timeout
            existing.request_payload = dict(request.payload or {})
            if request.correlation_id:
                existing.correlation_id = request.correlation_id
            existing.error_message = None
            existing.result_summary = {}
            existing.finished_at = None
            existing.started_at = utc_now()
            existing.status = WorkflowExecutionStatus.RECEIVED
            self._session.flush()
            return self._run(existing)

        # received (shouldn't linger) — continue
        return self._run(existing)

    def _persist_terminal(self, execution: WorkflowExecution) -> None:
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            logger.exception(
                "Failed to persist workflow terminal state id=%s status=%s",
                execution.id,
                execution.status,
            )
            raise

    def _run(self, execution: WorkflowExecution) -> WorkflowExecutionView:
        name = _as_name(execution.workflow_name)
        handler = self._handlers[name.value]
        execution.status = WorkflowExecutionStatus.RUNNING
        self._session.commit()

        started = time.monotonic()
        timeout = float(execution.timeout_seconds)
        try:
            result = handler(dict(execution.request_payload or {}), timeout)
            elapsed = time.monotonic() - started
            summary = result if isinstance(result, dict) else {"result": result}
            # Soft deadline: if the handler already completed successfully, keep SUCCEEDED
            # so retries do not re-run side effects. Record overrun for observability.
            if elapsed > timeout:
                logger.warning(
                    "workflow_soft_timeout_kept_success id=%s workflow=%s elapsed=%.3f timeout=%.3f",
                    execution.id,
                    name.value,
                    elapsed,
                    timeout,
                )
                summary = {
                    **summary,
                    "_soft_timeout": True,
                    "elapsed_seconds": round(elapsed, 3),
                    "timeout_seconds": timeout,
                }
            execution.status = WorkflowExecutionStatus.SUCCEEDED
            execution.result_summary = summary
            execution.error_message = None
            execution.finished_at = utc_now()
            agent_run_id = execution.result_summary.get("agent_run_id")
            if agent_run_id:
                try:
                    execution.agent_run_id = UUID(str(agent_run_id))
                except (ValueError, TypeError):
                    pass
            self._persist_terminal(execution)
            return self._to_view(execution)
        except WorkflowTimeoutError as exc:
            execution.status = WorkflowExecutionStatus.TIMED_OUT
            execution.error_message = exc.message
            execution.finished_at = utc_now()
            execution.result_summary = {"error": "timeout", "details": exc.details}
            self._persist_terminal(execution)
            logger.warning(
                "workflow_timed_out id=%s workflow=%s attempt=%s",
                execution.id,
                name.value,
                execution.attempt,
            )
            return self._to_view(execution, retryable=execution.attempt <= self._settings.n8n_max_execution_retries)
        except Exception as exc:  # noqa: BLE001 — boundary for orchestration failures
            execution.status = WorkflowExecutionStatus.FAILED
            execution.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            execution.finished_at = utc_now()
            execution.result_summary = {"error": type(exc).__name__}
            self._persist_terminal(execution)
            logger.exception(
                "workflow_failed id=%s workflow=%s attempt=%s",
                execution.id,
                name.value,
                execution.attempt,
            )
            return self._to_view(
                execution,
                retryable=execution.attempt <= self._settings.n8n_max_execution_retries,
            )

    def _find(self, name: WorkflowName, idempotency_key: str) -> WorkflowExecution | None:
        return self._session.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.workflow_name == name.value,
                WorkflowExecution.idempotency_key == idempotency_key,
            )
        )

    def _to_view(
        self,
        row: WorkflowExecution,
        *,
        idempotent_replay: bool = False,
        retryable: bool | None = None,
    ) -> WorkflowExecutionView:
        status = _as_status(row.status)
        if retryable is None:
            retryable = (
                status in _RETRYABLE
                and row.attempt <= self._settings.n8n_max_execution_retries
            )
        return WorkflowExecutionView(
            id=row.id,
            workflow_name=_as_name(row.workflow_name),
            idempotency_key=row.idempotency_key,
            status=status,
            attempt=row.attempt,
            timeout_seconds=row.timeout_seconds,
            trigger_source=row.trigger_source,
            started_at=row.started_at,
            finished_at=row.finished_at,
            result_summary=row.result_summary or {},
            error_message=row.error_message,
            agent_run_id=row.agent_run_id,
            correlation_id=row.correlation_id,
            idempotent_replay=idempotent_replay,
            retryable=bool(retryable),
            metadata=row.extra_metadata or {},
        )
