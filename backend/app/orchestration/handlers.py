"""Build thin agent/service adapters for n8n-triggered workflows.

Business logic stays in agents/services. This module only wires ports.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.audit import AuditAgent, AuditRequest
from app.agents.manager import ManagerAgent, ManagerRequest, RegistryExecutor
from app.agents.manager.schemas import DelegationResult
from app.agents.report import ReportAgent, ReportRequest
from app.agents.research import ResearchAgent, ResearchRequest
from app.approvals.service import ApprovalService
from app.config import Settings
from app.models import Company, CompanyScore
from app.models.enums import WorkflowName
from app.services.ai_service import build_ai_service
from app.services.browser_service import build_browser_service
from app.services.email_service import build_email_service
from app.services.follow_up_service import FollowUpService
from app.services.lead_scoring_service import LeadScoringService
from app.services.notification_service import build_notification_service
from app.services.search_service import build_search_service

logger = logging.getLogger(__name__)

WorkflowHandler = Any  # (payload: dict, timeout_seconds: float) -> dict


def _uuid_list(raw: Any) -> list[UUID]:
    if not raw:
        return []
    out: list[UUID] = []
    for item in raw:
        out.append(item if isinstance(item, UUID) else UUID(str(item)))
    return out


def build_manager_executor(session: Session, settings: Settings) -> RegistryExecutor:
    """Register full-cycle executors for Manager orchestration (thin adapters only)."""
    registry = RegistryExecutor()
    search = build_search_service(settings)
    browser = build_browser_service(settings, session=session)
    ai = build_ai_service(settings)
    approvals = ApprovalService(session, settings)

    def research_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        agent = ResearchAgent(
            session=session,
            search_service=search,
            browser_service=browser,
            settings=settings,
        )
        req = ResearchRequest(
            query=str(payload.get("query") or "local businesses website"),
            industry=payload.get("industry"),
            location=payload.get("location"),
            max_companies=payload.get("max_companies"),
            verify_with_browser=payload.get("verify_with_browser"),
            idempotency_key=payload.get("idempotency_key"),
            metadata={"timeout_seconds": timeout_seconds, "source": "manager_cycle"},
        )
        result = agent.run(req)
        return DelegationResult(
            status="succeeded" if result.status == "succeeded" else "failed",
            summary=f"companies_created={result.companies_created}",
            estimated_cost=result.estimated_cost,
            output=result.model_dump(mode="json"),
            retryable=result.status == "failed",
            error_message=result.error_message,
        )

    def scoring_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        svc = LeadScoringService(session)
        limit = int(payload.get("limit") or settings.max_companies_per_run)
        limit = max(1, min(limit, 50))
        ids = _uuid_list(payload.get("company_ids"))
        if payload.get("score_all_unscored"):
            scored_ids = set(session.scalars(select(CompanyScore.company_id)).all())
            all_ids = list(session.scalars(select(Company.id)).all())
            ids = [cid for cid in all_ids if cid not in scored_ids][:limit]
        else:
            ids = ids[:limit]
        scored = 0
        errors: list[str] = []
        for company_id in ids:
            try:
                svc.score_company(company_id, persist=True)
                scored += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{company_id}:{type(exc).__name__}")
        session.commit()
        status = "succeeded" if not errors else ("partial" if scored else "failed")
        return DelegationResult(
            status="succeeded" if status != "failed" else "failed",
            summary=f"scored={scored} errors={len(errors)}",
            estimated_cost=Decimal("0"),
            output={"scored_count": scored, "errors": errors[:20], "timeout_seconds": timeout_seconds},
            retryable=status == "failed",
            error_message="; ".join(errors[:5]) if errors and not scored else None,
        )

    def audit_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        agent = AuditAgent(
            session=session,
            search_service=search,
            browser_service=browser,
            ai_service=ai,
            settings=settings,
        )
        req = AuditRequest(
            company_ids=_uuid_list(payload.get("company_ids")),
            max_audits=payload.get("max_audits"),
            use_ai=payload.get("use_ai"),
            idempotency_key=payload.get("idempotency_key"),
            metadata={"timeout_seconds": timeout_seconds, "source": "manager_cycle"},
        )
        result = agent.run(req)
        ok = result.status in ("succeeded", "partial")
        return DelegationResult(
            status="succeeded" if ok else "failed",
            summary=f"audits_completed={result.audits_completed}",
            estimated_cost=result.estimated_cost,
            output={
                **result.model_dump(mode="json"),
                "audits_completed": result.audits_completed,
            },
            retryable=result.status == "failed",
            error_message=result.error_message,
        )

    def sales_draft_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from app.agents.sales import SalesAgent, SalesRequest

        agent = SalesAgent(
            session=session,
            settings=settings,
            ai_service=ai,
            approval_service=approvals,
        )
        req = SalesRequest(
            company_id=UUID(str(payload["company_id"])),
            lead_id=UUID(str(payload["lead_id"])),
            company_score_id=UUID(str(payload["company_score_id"])) if payload.get("company_score_id") else None,
            company_audit_id=UUID(str(payload["company_audit_id"])) if payload.get("company_audit_id") else None,
            use_ai=payload.get("use_ai"),
            idempotency_key=payload.get("idempotency_key"),
            metadata={"timeout_seconds": timeout_seconds, "source": "manager_cycle"},
        )
        result = agent.run(req)
        outreach_id = str(result.outreach.outreach_id) if result.outreach else None
        ok = result.status in ("succeeded", "partial") and outreach_id
        return DelegationResult(
            status="succeeded" if ok else "failed",
            summary=f"draft_outreach={outreach_id or 'none'}",
            estimated_cost=result.estimated_cost,
            output={
                "outreach_id": outreach_id,
                "status": result.status,
                "send_attempted": result.send_attempted,
            },
            retryable=result.status == "failed",
            error_message=result.error_message,
        )

    def sales_send_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from app.agents.sales import SalesAgent

        agent = SalesAgent(
            session=session,
            settings=settings,
            ai_service=ai,
            approval_service=approvals,
        )
        outreach_id = UUID(str(payload["outreach_id"]))
        try:
            message = agent.send_outreach(outreach_id)
            return DelegationResult(
                status="succeeded",
                summary=f"sent_outreach={outreach_id}",
                estimated_cost=getattr(message, "estimated_cost", Decimal("0")) or Decimal("0"),
                output={
                    "outreach_id": str(outreach_id),
                    "outbound_message_id": str(getattr(message, "id", "")),
                    "timeout_seconds": timeout_seconds,
                },
                retryable=False,
            )
        except Exception as exc:  # noqa: BLE001
            return DelegationResult(
                status="failed",
                summary=f"send_failed:{type(exc).__name__}",
                estimated_cost=Decimal("0"),
                output={"outreach_id": str(outreach_id)},
                retryable=True,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    def followup_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        email = build_email_service(session, settings, approval_service=approvals)
        service = FollowUpService(
            session=session,
            settings=settings,
            approval_service=approvals,
            email_service=email,
        )
        limit = int(payload.get("limit") or 5)
        results = service.process_due(limit=limit)
        return DelegationResult(
            status="succeeded",
            summary=f"followups_processed={len(results)}",
            estimated_cost=Decimal("0"),
            output={
                "processed": len(results),
                "actions": [r.action for r in results],
                "timeout_seconds": timeout_seconds,
            },
            retryable=False,
        )

    def responses_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from app.agents.manager.business_state import inspect_business_state

        state = inspect_business_state(session)
        return DelegationResult(
            status="succeeded",
            summary=f"responses_recorded={state.responses_recorded}",
            estimated_cost=Decimal("0"),
            output={
                "responses_recorded": state.responses_recorded,
                "follow_ups_due": state.follow_ups_due,
                "pending_approvals": state.pending_approvals,
                "customers_active": state.customers_active,
                "timeout_seconds": timeout_seconds,
            },
            retryable=False,
        )

    def delivery_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from app.agents.delivery import DeliveryAgent, DeliveryRequest

        agent = DeliveryAgent(session=session, settings=settings, approval_service=approvals)
        req = DeliveryRequest(
            lead_id=UUID(str(payload["lead_id"])),
            project_name=payload.get("project_name"),
            idempotency_key=payload.get("idempotency_key"),
            metadata={"timeout_seconds": timeout_seconds, "source": "manager_cycle"},
        )
        result = agent.run(req)
        ok = result.status in ("succeeded", "partial") and result.project_id
        return DelegationResult(
            status="succeeded" if ok else "failed",
            summary=f"project_id={result.project_id}",
            estimated_cost=result.estimated_cost,
            output={
                "project_id": str(result.project_id) if result.project_id else None,
                "customer_id": str(result.customer_id) if result.customer_id else None,
                "status": result.status,
            },
            retryable=result.status == "failed",
            error_message=result.error_message,
        )

    def finance_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from datetime import datetime, timezone

        from app.agents.finance import FinanceAgent, FinanceCalculateRequest

        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        agent = FinanceAgent(session=session, settings=settings, approval_service=approvals)
        req = FinanceCalculateRequest(
            period_start=period_start,
            period_end=now,
            currency=str(payload.get("currency") or "USD"),
            lead_count=int(payload.get("lead_count") or 0),
            qualified_lead_count=int(payload.get("qualified_lead_count") or 0),
            customer_count=int(payload.get("customer_count") or 0),
            idempotency_key=payload.get("idempotency_key"),
            metadata={"timeout_seconds": timeout_seconds, "source": "manager_cycle"},
        )
        result = agent.run(req)
        metric = result.metric
        return DelegationResult(
            status="succeeded" if result.status == "succeeded" else "failed",
            summary=(
                f"profit={metric.gross_profit} mrr={metric.mrr}" if metric else "finance_failed"
            ),
            estimated_cost=result.estimated_cost,
            output={
                "metric_id": str(metric.id) if metric else None,
                "profit": str(metric.gross_profit) if metric else None,
                "mrr": str(metric.mrr) if metric else None,
                "total_revenue": str(metric.total_revenue) if metric else None,
                "total_costs": str(metric.total_costs) if metric else None,
                "roi": str(metric.roi) if metric and metric.roi is not None else None,
            },
            retryable=result.status == "failed",
            error_message=result.error_message,
        )

    def report_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from app.models.enums import ReportPeriodType

        agent = ReportAgent(session=session, settings=settings, approval_service=approvals)
        period = payload.get("period_type") or ReportPeriodType.DAILY.value
        req = ReportRequest(
            period_type=ReportPeriodType(period),
            currency=str(payload.get("currency") or "USD"),
            idempotency_key=payload.get("idempotency_key"),
            metadata={"timeout_seconds": timeout_seconds, "source": "manager_cycle"},
        )
        result = agent.run(req)
        report_id = str(result.report.id) if result.report else None
        return DelegationResult(
            status="succeeded" if result.status == "succeeded" else "failed",
            summary=f"report_id={report_id}",
            estimated_cost=result.estimated_cost,
            output={"report_id": report_id, "status": result.status},
            retryable=result.status == "failed",
            error_message=result.error_message,
        )

    def learning_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        from app.agents.manager.business_state import inspect_business_state
        from app.agents.manager.cycle import CycleGoal, recommend_next_strategy

        state = inspect_business_state(session)
        target_mrr = payload.get("target_mrr")
        cost_cap = payload.get("max_monthly_operating_cost")
        goal = CycleGoal(
            target_qualified_leads=int(payload.get("target_qualified_leads") or 10),
            target_mrr=Decimal(str(target_mrr)) if target_mrr not in (None, "") else None,
            max_monthly_operating_cost=Decimal(str(cost_cap)) if cost_cap not in (None, "") else None,
            full_cycle=True,
            currency_hint="UNKNOWN",
        )
        rec = recommend_next_strategy(goal=goal, state=state)
        return DelegationResult(
            status="succeeded",
            summary=f"goal_met={rec['goal_met']} priorities={','.join(rec['priorities'][:3])}",
            estimated_cost=Decimal("0"),
            output={**rec, "timeout_seconds": timeout_seconds},
            retryable=False,
        )

    def strategy_fn(payload: dict, timeout_seconds: float) -> DelegationResult:
        # Only reachable after human approval of YELLOW strategy.major_change.
        return DelegationResult(
            status="succeeded",
            summary="strategy_change_recorded_awaiting_human_execution",
            estimated_cost=Decimal("0"),
            output={
                "recorded": True,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "note": "Major strategy changes remain human-owned after approval.",
            },
            retryable=False,
        )

    registry.register("research", "discover_companies", research_fn)
    registry.register("scoring", "score_companies", scoring_fn)
    registry.register("audit", "audit_digital_presence", audit_fn)
    registry.register("sales", "draft_outreach", sales_draft_fn)
    registry.register("sales", "send_outreach", sales_send_fn)
    registry.register("sales", "first_outreach", sales_send_fn)
    registry.register("followup", "process_due", followup_fn)
    registry.register("responses", "monitor", responses_fn)
    registry.register("delivery", "create_project", delivery_fn)
    registry.register("finance", "calculate_metrics", finance_fn)
    registry.register("report", "generate", report_fn)
    registry.register("learning", "evaluate_performance", learning_fn)
    registry.register("strategy", "major_change", strategy_fn)
    return registry


def build_default_handlers(session: Session, settings: Settings) -> dict[str, WorkflowHandler]:
    """Map workflow name → callable returning a JSON-serializable result dict."""

    def daily_cycle(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        # Clamp manager runtime to webhook timeout (no uncontrolled long runs).
        runtime = min(int(timeout_seconds), settings.max_agent_runtime_seconds)
        clamped = settings.model_copy(update={"max_agent_runtime_seconds": runtime})
        agent = ManagerAgent(
            session=session,
            executor=build_manager_executor(session, clamped),
            settings=clamped,
            approval_service=ApprovalService(session, clamped),
        )
        goal = str(
            payload.get("goal")
            or "Reach €1,000 MRR while keeping operating costs below €150/month."
        )
        req = ManagerRequest(
            goal=goal,
            target_qualified_leads=payload.get("target_qualified_leads"),
            industry=payload.get("industry"),
            location=payload.get("location"),
            query=payload.get("query"),
            idempotency_key=payload.get("manager_idempotency_key"),
            metadata={"source": "n8n", "workflow": WorkflowName.DAILY_CYCLE.value},
        )
        result = agent.run(req)
        return {
            "manager_status": result.status,
            "manager_run_id": str(result.manager_run_id),
            "agent_run_id": str(result.agent_run_id),
            "plan_summary": result.plan_summary,
            "tasks_succeeded": result.tasks_succeeded,
            "tasks_failed": result.tasks_failed,
            "estimated_cost": str(result.estimated_cost),
            "awaiting_approval": result.status == "awaiting_approval",
            "stop_reason": result.stop_reason,
            "error_message": result.error_message,
        }

    def research(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        agent = ResearchAgent(
            session=session,
            search_service=build_search_service(settings),
            browser_service=build_browser_service(settings, session=session),
            settings=settings,
        )
        query = str(payload.get("query") or "local businesses website")
        req = ResearchRequest(
            query=query,
            industry=payload.get("industry"),
            location=payload.get("location"),
            max_companies=payload.get("max_companies"),
            verify_with_browser=payload.get("verify_with_browser"),
            idempotency_key=payload.get("agent_idempotency_key"),
            metadata={"source": "n8n", "timeout_seconds": timeout_seconds},
        )
        result = agent.run(req)
        return {
            "status": result.status,
            "agent_run_id": str(result.agent_run_id),
            "companies_created": result.companies_created,
            "estimated_cost": str(result.estimated_cost),
            "error_message": result.error_message,
        }

    def audit(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        agent = AuditAgent(
            session=session,
            search_service=build_search_service(settings),
            browser_service=build_browser_service(settings, session=session),
            ai_service=build_ai_service(settings),
            settings=settings,
        )
        req = AuditRequest(
            company_ids=_uuid_list(payload.get("company_ids")),
            max_audits=payload.get("max_audits"),
            use_ai=payload.get("use_ai"),
            idempotency_key=payload.get("agent_idempotency_key"),
            metadata={"source": "n8n", "timeout_seconds": timeout_seconds},
        )
        result = agent.run(req)
        return {
            "status": result.status,
            "agent_run_id": str(result.agent_run_id),
            "audits_completed": result.audits_completed,
            "audits_failed": result.audits_failed,
            "estimated_cost": str(result.estimated_cost),
            "error_message": result.error_message,
        }

    def outreach_approval_queue(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        """Surface pending approvals + expire due ones. NEVER approve or reject."""
        approvals = ApprovalService(session, settings)
        expired = approvals.expire_due_approvals()
        limit = int(payload.get("limit") or 50)
        pending = approvals.list_pending(limit=limit)
        session.commit()
        return {
            "expired_count": expired,
            "pending_count": len(pending),
            "pending": [
                {
                    "id": str(p.id),
                    "action_type": p.action_type,
                    "risk_level": p.risk_level.value if hasattr(p.risk_level, "value") else str(p.risk_level),
                    "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                    "description": p.description[:200],
                    "requested_by": p.requested_by,
                    "requested_at": p.requested_at.isoformat(),
                }
                for p in pending
            ],
            "auto_approved": False,
            "approval_bypass_blocked": True,
            "timeout_seconds": timeout_seconds,
            "note": "Human must resolve via ApprovalResolver; n8n cannot approve.",
        }

    def follow_ups(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        approvals = ApprovalService(session, settings)
        email = build_email_service(session, settings, approval_service=approvals)
        service = FollowUpService(
            session=session,
            settings=settings,
            approval_service=approvals,
            email_service=email,
        )
        limit = int(payload.get("limit") or 5)
        results = service.process_due(limit=limit)
        return {
            "processed": len(results),
            "actions": [
                {
                    "sequence_id": str(r.sequence_id),
                    "action": r.action,
                    "stop_reason": r.stop_reason,
                }
                for r in results
            ],
            "sends_without_approval": 0,
            "timeout_seconds": timeout_seconds,
        }

    def daily_report(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        approvals = ApprovalService(session, settings)
        agent = ReportAgent(session=session, settings=settings, approval_service=approvals)
        from app.models.enums import ReportPeriodType

        period = payload.get("period_type") or ReportPeriodType.DAILY.value
        req = ReportRequest(
            period_type=ReportPeriodType(period),
            currency=str(payload.get("currency") or "USD"),
            idempotency_key=payload.get("agent_idempotency_key"),
            metadata={"source": "n8n", "timeout_seconds": timeout_seconds},
        )
        result = agent.run(req)
        report_id = None
        if result.report is not None:
            report_id = str(result.report.id)
            try:
                build_notification_service(session, settings).notify_daily_ceo_report(
                    report_id=result.report.id,
                    title=result.report.title or "Daily CEO report",
                    summary=None,
                )
                session.commit()
            except Exception:  # noqa: BLE001
                logger.debug("daily_report_notify_skipped", exc_info=True)
        return {
            "status": result.status,
            "agent_run_id": str(result.agent_run_id),
            "report_id": report_id,
            "error_message": result.error_message,
        }

    def error_monitoring(payload: dict, timeout_seconds: float) -> dict[str, Any]:
        from datetime import timedelta

        from app.models import AgentRun, WorkflowExecution
        from app.models.base import utc_now
        from app.models.enums import AgentRunStatus, WorkflowExecutionStatus

        lookback_hours = int(payload.get("lookback_hours") or 24)
        since = utc_now() - timedelta(hours=max(1, min(lookback_hours, 168)))
        failed_runs = list(
            session.scalars(
                select(AgentRun)
                .where(
                    AgentRun.status == AgentRunStatus.FAILED.value,
                    AgentRun.started_at >= since,
                )
                .order_by(AgentRun.started_at.desc())
                .limit(20)
            )
        )
        failed_workflows = list(
            session.scalars(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.status.in_(
                        [
                            WorkflowExecutionStatus.FAILED.value,
                            WorkflowExecutionStatus.TIMED_OUT.value,
                        ]
                    ),
                    WorkflowExecution.started_at >= since,
                )
                .order_by(WorkflowExecution.started_at.desc())
                .limit(20)
            )
        )
        critical_notified = 0
        notifier = build_notification_service(session, settings)
        for run in failed_runs[:5]:
            ref = f"agent_run:{run.id}"
            record = notifier.notify_critical_failure(
                source=f"agent:{run.agent_name}",
                message=run.error_message or run.output_summary or "agent run failed",
                reference=ref,
            )
            if record is not None:
                critical_notified += 1
        for wf in failed_workflows[:5]:
            ref = f"workflow:{wf.id}"
            record = notifier.notify_critical_failure(
                source=f"workflow:{wf.workflow_name}",
                message=wf.error_message or wf.status,
                reference=ref,
            )
            if record is not None:
                critical_notified += 1
        session.commit()
        return {
            "lookback_hours": lookback_hours,
            "failed_agent_runs": len(failed_runs),
            "failed_workflow_executions": len(failed_workflows),
            "critical_notifications_attempted": critical_notified,
            "timeout_seconds": timeout_seconds,
            "samples": {
                "agent_runs": [
                    {
                        "id": str(r.id),
                        "agent_name": r.agent_name,
                        "error_message": (r.error_message or "")[:200],
                    }
                    for r in failed_runs[:5]
                ],
                "workflows": [
                    {
                        "id": str(w.id),
                        "workflow_name": str(w.workflow_name),
                        "status": str(w.status),
                        "error_message": (w.error_message or "")[:200],
                    }
                    for w in failed_workflows[:5]
                ],
            },
        }

    return {
        WorkflowName.DAILY_CYCLE.value: daily_cycle,
        WorkflowName.RESEARCH.value: research,
        WorkflowName.AUDIT.value: audit,
        WorkflowName.OUTREACH_APPROVAL_QUEUE.value: outreach_approval_queue,
        WorkflowName.FOLLOW_UPS.value: follow_ups,
        WorkflowName.DAILY_REPORT.value: daily_report,
        WorkflowName.ERROR_MONITORING.value: error_monitoring,
    }
