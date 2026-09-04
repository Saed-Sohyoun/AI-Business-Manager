"""Authenticated n8n webhook endpoints — thin orchestration triggers only."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.enums import WorkflowExecutionStatus, WorkflowName
from app.orchestration.auth import verify_n8n_webhook
from app.orchestration.schemas import (
    WorkflowExecutionView,
    WorkflowTriggerRequest,
    WorkflowTriggerResponse,
)
from app.orchestration.service import N8nOrchestrationService

router = APIRouter(prefix="/n8n", tags=["n8n"])


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def require_n8n_auth(request: Request) -> None:
    verify_n8n_webhook(request, _settings(request))


def get_orchestration_service(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> N8nOrchestrationService:
    cfg = _settings(request)
    handlers = getattr(request.app.state, "n8n_handlers", None)
    return N8nOrchestrationService(session=session, settings=cfg, handlers=handlers)


def _status_code(view: WorkflowExecutionView) -> int:
    status = view.status
    if status == WorkflowExecutionStatus.SUCCEEDED:
        return 200
    if status == WorkflowExecutionStatus.TIMED_OUT:
        return 504
    if status == WorkflowExecutionStatus.FAILED:
        return 502
    if status == WorkflowExecutionStatus.RUNNING:
        return 409
    return 200


def _trigger(
    *,
    workflow: WorkflowName,
    body: WorkflowTriggerRequest,
    service: N8nOrchestrationService,
    response: Response,
) -> WorkflowTriggerResponse:
    view = service.trigger(workflow, body)
    response.status_code = _status_code(view)
    return WorkflowTriggerResponse(execution=view)


@router.post(
    "/webhooks/daily-cycle",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_daily_cycle(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.DAILY_CYCLE,
        body=body,
        service=service,
        response=response,
    )


@router.post(
    "/webhooks/research",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_research(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.RESEARCH,
        body=body,
        service=service,
        response=response,
    )


@router.post(
    "/webhooks/audit",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_audit(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.AUDIT,
        body=body,
        service=service,
        response=response,
    )


@router.post(
    "/webhooks/outreach-approval-queue",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_outreach_approval_queue(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.OUTREACH_APPROVAL_QUEUE,
        body=body,
        service=service,
        response=response,
    )


@router.post(
    "/webhooks/follow-ups",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_follow_ups(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.FOLLOW_UPS,
        body=body,
        service=service,
        response=response,
    )


@router.post(
    "/webhooks/daily-report",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_daily_report(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.DAILY_REPORT,
        body=body,
        service=service,
        response=response,
    )


@router.post(
    "/webhooks/error-monitoring",
    response_model=WorkflowTriggerResponse,
    dependencies=[Depends(require_n8n_auth)],
)
def webhook_error_monitoring(
    body: WorkflowTriggerRequest,
    response: Response,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowTriggerResponse:
    return _trigger(
        workflow=WorkflowName.ERROR_MONITORING,
        body=body,
        service=service,
        response=response,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=WorkflowExecutionView,
    dependencies=[Depends(require_n8n_auth)],
)
def get_execution(
    execution_id: UUID,
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
) -> WorkflowExecutionView:
    return service.get_execution(execution_id)


@router.get(
    "/executions",
    response_model=list[WorkflowExecutionView],
    dependencies=[Depends(require_n8n_auth)],
)
def list_executions(
    service: Annotated[N8nOrchestrationService, Depends(get_orchestration_service)],
    workflow_name: WorkflowName | None = None,
    limit: int = 50,
) -> list[WorkflowExecutionView]:
    return service.list_executions(workflow_name=workflow_name, limit=limit)
