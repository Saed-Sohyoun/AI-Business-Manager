"""Owner control-plane HTTP API."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.exceptions import ForbiddenError
from app.middleware.request_id import get_request_id
from app.models.owner_account import OwnerAccount
from app.owner.alerts import OwnerAlertService
from app.owner.approvals import OwnerApprovalService
from app.owner.auth import OwnerDep
from app.owner.controls import SystemControlService
from app.owner.dashboard import DashboardService
from app.owner.schemas import (
    ActiveWorkListView,
    ApprovalDecisionView,
    ControlChangeBody,
    ControlStateView,
    DashboardSummaryView,
    DecisionNoteBody,
    OwnerAlertListView,
    SecurityEventListView,
    SystemStatusView,
)
from app.owner.schemas_commands import (
    ExecutionView,
    FindOpportunitiesRequest,
    FindOpportunitiesResponse,
    GenerateReportRequest,
    LoginRequest,
    LoginResponse,
    SessionMeView,
)
from app.owner.schemas_pilot import PilotExperimentCreate
from app.owner.security_query import SecurityEventQueryService
from app.owner.session_auth import SESSION_COOKIE, SessionAuthService
from app.owner.status import SystemStatusService
from app.owner.work import ActiveWorkService
from app.schemas.common import DataResponse
from app.owner.commands import OwnerCommandService
from app.owner.customers_catalog import CustomerCatalogService
from app.owner.opportunities import OpportunityCatalogService
from app.owner.reports_catalog import ReportCatalogService

router = APIRouter(prefix="/owner", tags=["owner"])


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _control_view(state) -> ControlStateView:
    return ControlStateView(
        system_mode=state.system_mode,
        ai_operations_enabled=state.ai_operations_enabled,
        outbound_enabled=state.outbound_enabled,
        spending_enabled=state.spending_enabled,
        browser_automation_enabled=state.browser_automation_enabled,
        safe_mode_reason=state.safe_mode_reason,
        pause_reason=state.pause_reason,
        last_changed_by=state.last_changed_by,
        last_changed_at=state.last_changed_at,
    )


# ---- Approvals ---------------------------------------------------------------


@router.get("/approvals", response_model=DataResponse[list[ApprovalDecisionView]])
def list_approvals(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[str | None, Query()] = None,
) -> DataResponse[list[ApprovalDecisionView]]:
    owner.require("owner.read_approvals")
    items = OwnerApprovalService(session, _settings(request)).list_approvals(
        limit=limit, status=status
    )
    return DataResponse(data=items, request_id=get_request_id(request))


@router.get("/approvals/{approval_id}", response_model=DataResponse[ApprovalDecisionView])
def get_approval(
    request: Request,
    approval_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[ApprovalDecisionView]:
    owner.require("owner.read_approvals")
    view = OwnerApprovalService(session, _settings(request)).get_approval(approval_id)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=DataResponse[ApprovalDecisionView],
)
def approve_approval(
    request: Request,
    approval_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: DecisionNoteBody | None = None,
) -> DataResponse[ApprovalDecisionView]:
    owner.require("owner.resolve_approvals")
    note = body.note if body else None
    view = OwnerApprovalService(session, _settings(request)).approve(
        approval_id,
        owner_id=owner.owner_id,
        note=note,
        request_id=owner.request_id,
    )
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=DataResponse[ApprovalDecisionView],
)
def reject_approval(
    request: Request,
    approval_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: DecisionNoteBody | None = None,
) -> DataResponse[ApprovalDecisionView]:
    owner.require("owner.resolve_approvals")
    note = body.note if body else None
    view = OwnerApprovalService(session, _settings(request)).reject(
        approval_id,
        owner_id=owner.owner_id,
        note=note,
        request_id=owner.request_id,
    )
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post(
    "/approvals/{approval_id}/cancel",
    response_model=DataResponse[ApprovalDecisionView],
)
def cancel_approval(
    request: Request,
    approval_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: DecisionNoteBody | None = None,
) -> DataResponse[ApprovalDecisionView]:
    owner.require("owner.resolve_approvals")
    note = body.note if body else None
    view = OwnerApprovalService(session, _settings(request)).cancel(
        approval_id,
        owner_id=owner.owner_id,
        note=note,
    )
    return DataResponse(data=view, request_id=get_request_id(request))


# ---- System controls ---------------------------------------------------------


@router.get("/system/status", response_model=DataResponse[SystemStatusView])
def system_status(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[SystemStatusView]:
    owner.require("owner.read_system_status")
    view = SystemStatusService(session, _settings(request)).status()
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post("/system/pause-all", response_model=DataResponse[ControlStateView])
def pause_all(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.pause_all")
    state = SystemControlService(session).pause_all(
        actor=owner.owner_id,
        reason=body.reason if body else None,
    )
    from app.owner.alerts import OwnerAlertService
    from app.models.system_mode import AlertPriority

    OwnerAlertService(session).upsert_alert(
        dedupe_key="system:paused_by_owner",
        title="System paused by owner",
        body=state.pause_reason or "All AI operations are paused.",
        priority=AlertPriority.CRITICAL,
        source="owner",
        details={"actor": owner.owner_id},
        commit=True,
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/pause-ai", response_model=DataResponse[ControlStateView])
def pause_ai(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.pause_ai")
    state = SystemControlService(session).set_control(
        "ai_operations", enabled=False, actor=owner.owner_id, reason=body.reason if body else None
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/resume-ai", response_model=DataResponse[ControlStateView])
def resume_ai(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.resume_operations")
    state = SystemControlService(session).set_control(
        "ai_operations", enabled=True, actor=owner.owner_id, reason=body.reason if body else None
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/pause-outbound", response_model=DataResponse[ControlStateView])
def pause_outbound(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.pause_outbound")
    state = SystemControlService(session).set_control(
        "outbound", enabled=False, actor=owner.owner_id, reason=body.reason if body else None
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/resume-outbound", response_model=DataResponse[ControlStateView])
def resume_outbound(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.resume_operations")
    controls = SystemControlService(session)
    snap = controls.get_or_create()
    if snap.system_mode == "safe_mode":
        raise ForbiddenError(
            "Cannot resume outbound while SAFE_MODE is active — clear safe mode first",
            details={"system_mode": snap.system_mode},
        )
    state = controls.set_control(
        "outbound", enabled=True, actor=owner.owner_id, reason=body.reason if body else None
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/pause-spending", response_model=DataResponse[ControlStateView])
def pause_spending(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.pause_spending")
    state = SystemControlService(session).set_control(
        "spending", enabled=False, actor=owner.owner_id, reason=body.reason if body else None
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/resume-spending", response_model=DataResponse[ControlStateView])
def resume_spending(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.resume_operations")
    controls = SystemControlService(session)
    snap = controls.get_or_create()
    if snap.system_mode == "safe_mode":
        raise ForbiddenError(
            "Cannot resume spending while SAFE_MODE is active — clear safe mode first",
            details={"system_mode": snap.system_mode},
        )
    state = controls.set_control(
        "spending", enabled=True, actor=owner.owner_id, reason=body.reason if body else None
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/pause-browser", response_model=DataResponse[ControlStateView])
def pause_browser(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.pause_browser")
    state = SystemControlService(session).set_control(
        "browser_automation",
        enabled=False,
        actor=owner.owner_id,
        reason=body.reason if body else None,
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/resume-browser", response_model=DataResponse[ControlStateView])
def resume_browser(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.resume_operations")
    state = SystemControlService(session).set_control(
        "browser_automation",
        enabled=True,
        actor=owner.owner_id,
        reason=body.reason if body else None,
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/clear-safe-mode", response_model=DataResponse[ControlStateView])
def clear_safe_mode(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    owner.require("owner.manage_safe_mode")
    state = SystemControlService(session).clear_safe_mode(
        actor=owner.owner_id,
        reason=body.reason if body else None,
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


@router.post("/system/enter-safe-mode", response_model=DataResponse[ControlStateView])
def enter_safe_mode(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: ControlChangeBody | None = None,
) -> DataResponse[ControlStateView]:
    """Owner may force SAFE_MODE for testing / ops; machine triggers also exist."""
    owner.require("owner.manage_safe_mode")
    state = SystemControlService(session).enter_safe_mode(
        reason=(body.reason if body and body.reason else "Owner entered safe mode"),
        actor=owner.owner_id,
    )
    return DataResponse(data=_control_view(state), request_id=get_request_id(request))


# ---- Dashboard / work / alerts / security ------------------------------------


@router.get("/dashboard/summary", response_model=DataResponse[DashboardSummaryView])
def dashboard_summary(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[DashboardSummaryView]:
    owner.require("owner.read_dashboard")
    view = DashboardService(session).summary()
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/work/active", response_model=DataResponse[ActiveWorkListView])
def active_work(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DataResponse[ActiveWorkListView]:
    owner.require("owner.read_work")
    view = ActiveWorkService(session).list_active(limit=limit)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/alerts", response_model=DataResponse[OwnerAlertListView])
def list_alerts(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DataResponse[OwnerAlertListView]:
    owner.require("owner.read_alerts")
    view = OwnerAlertService(session).list_alerts(limit=limit)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/security-events", response_model=DataResponse[SecurityEventListView])
def list_security_events(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DataResponse[SecurityEventListView]:
    owner.require("owner.read_security_events")
    view = SecurityEventQueryService(session).list_events(limit=limit)
    return DataResponse(data=view, request_id=get_request_id(request))


# ---- Auth (session) ----------------------------------------------------------


@router.post("/auth/login")
def owner_login(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    body: LoginRequest,
) -> JSONResponse:
    auth = SessionAuthService(session, _settings(request))
    client_host = request.client.host if request.client else None
    sess_row, raw_token = auth.login(
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("User-Agent"),
        ip_hint=client_host,
    )
    account = session.get(OwnerAccount, sess_row.owner_id)
    assert account is not None
    payload = LoginResponse(
        email=account.email,
        display_name=account.display_name,
        csrf_token=sess_row.csrf_token,
        auth_method="session",
    )
    body_out = DataResponse(
        data=payload, request_id=get_request_id(request)
    ).model_dump(mode="json")
    response = JSONResponse(content=body_out)
    cfg = _settings(request)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        secure=bool(cfg.session_cookie_secure or cfg.is_production),
        samesite="lax",
        max_age=int(cfg.owner_session_ttl_hours * 3600),
        path="/",
    )
    return response


@router.post("/auth/logout")
def owner_logout(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    raw = request.cookies.get(SESSION_COOKIE)
    SessionAuthService(session, _settings(request)).logout(raw)
    body_out = DataResponse(
        data={"ok": True},
        request_id=get_request_id(request),
    ).model_dump(mode="json")
    response = JSONResponse(content=body_out)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/me", response_model=DataResponse[SessionMeView])
def owner_me(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[SessionMeView]:
    display = "Owner"
    csrf = owner.csrf_token
    email = owner.owner_id
    if owner.auth_method == "session":
        raw = request.cookies.get(SESSION_COOKIE)
        resolved = SessionAuthService(session, _settings(request)).resolve_session(raw)
        if resolved:
            account, sess = resolved
            display = account.display_name
            email = account.email
            csrf = sess.csrf_token
    return DataResponse(
        data=SessionMeView(
            email=email,
            display_name=display,
            auth_method=owner.auth_method,
            csrf_token=csrf,
            production_locked=not _settings(request).allow_production_mode,
        ),
        request_id=get_request_id(request),
    )


# ---- Commands / executions ---------------------------------------------------


@router.post(
    "/commands/find-opportunities",
    status_code=202,
    response_model=DataResponse[FindOpportunitiesResponse],
)
def find_opportunities(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: FindOpportunitiesRequest,
) -> DataResponse[FindOpportunitiesResponse]:
    owner.require("owner.launch_commands")
    view = OwnerCommandService(session, _settings(request)).find_opportunities(
        body,
        owner_id=owner.owner_id,
        correlation_id=owner.request_id,
    )
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/executions", response_model=DataResponse[list[ExecutionView]])
def list_executions(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DataResponse[list[ExecutionView]]:
    owner.require("owner.read_executions")
    items = OwnerCommandService(session, _settings(request)).list_executions(limit=limit)
    return DataResponse(data=items, request_id=get_request_id(request))


@router.get("/executions/{execution_id}", response_model=DataResponse[ExecutionView])
def get_execution(
    request: Request,
    execution_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[ExecutionView]:
    owner.require("owner.read_executions")
    view = OwnerCommandService(session, _settings(request)).get_execution(execution_id)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post("/executions/{execution_id}/cancel", response_model=DataResponse[ExecutionView])
def cancel_execution(
    request: Request,
    execution_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[ExecutionView]:
    owner.require("owner.cancel_executions")
    view = OwnerCommandService(session, _settings(request)).cancel(
        execution_id, owner_id=owner.owner_id
    )
    return DataResponse(data=view, request_id=get_request_id(request))


# ---- Catalogs ----------------------------------------------------------------


@router.get("/opportunities")
def list_opportunities(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query()] = None,
    min_score: Annotated[int | None, Query()] = None,
    max_score: Annotated[int | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> DataResponse:
    owner.require("owner.read_opportunities")
    view = OpportunityCatalogService(session).list_opportunities(
        limit=limit,
        offset=offset,
        q=q,
        min_score=min_score,
        max_score=max_score,
        lifecycle=status,
    )
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    request: Request,
    opportunity_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse:
    owner.require("owner.read_opportunities")
    view = OpportunityCatalogService(session).get_opportunity(opportunity_id)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/customers")
def list_customers(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query()] = None,
) -> DataResponse:
    owner.require("owner.read_customers")
    view = CustomerCatalogService(session).list_customers(limit=limit, offset=offset, q=q)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/customers/{customer_id}")
def get_customer(
    request: Request,
    customer_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse:
    owner.require("owner.read_customers")
    view = CustomerCatalogService(session).get_customer(customer_id)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/reports")
def list_reports(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DataResponse:
    owner.require("owner.read_reports")
    view = ReportCatalogService(session, _settings(request)).list_reports(
        limit=limit, offset=offset
    )
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/reports/{report_id}")
def get_report(
    request: Request,
    report_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse:
    owner.require("owner.read_reports")
    view = ReportCatalogService(session, _settings(request)).get_report(report_id)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post("/reports/generate", status_code=202)
def generate_report(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: GenerateReportRequest,
) -> DataResponse:
    owner.require("owner.generate_reports")
    view = ReportCatalogService(session, _settings(request)).generate_async(
        period_type=body.period_type,
        idempotency_key=body.idempotency_key,
        owner_id=owner.owner_id,
        correlation_id=owner.request_id,
    )
    return DataResponse(data=view, request_id=get_request_id(request))


# ---- Wave 5 readiness & pilot experiment ------------------------------------


@router.get("/readiness")
def owner_readiness(
    request: Request,
    owner: OwnerDep,
) -> DataResponse:
    """Pilot launch readiness — never unlocks production or returns secrets."""
    owner.require("owner.read_readiness")
    from app.owner.readiness import ReadinessService

    view = ReadinessService(_settings(request)).evaluate()
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/pilot/experiment")
def get_pilot_experiment(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse:
    owner.require("owner.manage_pilot_experiment")
    from app.pilot.experiment import PilotExperimentService

    view = PilotExperimentService(session, _settings(request)).get_active()
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post("/pilot/experiment", status_code=201)
def create_pilot_experiment(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
    body: PilotExperimentCreate,
) -> DataResponse:
    owner.require("owner.manage_pilot_experiment")
    from app.pilot.experiment import PilotExperimentService

    view = PilotExperimentService(session, _settings(request)).create_draft(body)
    return DataResponse(data=view, request_id=get_request_id(request))


@router.post("/pilot/experiment/{experiment_id}/approve-niche")
def approve_pilot_niche(
    request: Request,
    experiment_id: UUID,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse:
    owner.require("owner.manage_pilot_experiment")
    from app.pilot.experiment import PilotExperimentService

    view = PilotExperimentService(session, _settings(request)).approve_niche(
        experiment_id, actor=owner.owner_id
    )
    return DataResponse(data=view, request_id=get_request_id(request))


@router.get("/pilot/status")
def owner_pilot_status(
    request: Request,
    owner: OwnerDep,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse:
    """Observability counters from DB only — no invented research results."""
    owner.require("owner.read_readiness")
    from app.pilot.experiment import PilotExperimentService

    view = PilotExperimentService(session, _settings(request)).observability_status()
    return DataResponse(data=view, request_id=get_request_id(request))
