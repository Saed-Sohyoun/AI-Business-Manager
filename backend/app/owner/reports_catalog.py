"""Owner reports catalog — BusinessReport rows only."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.report import ReportAgent
from app.agents.report.schemas import ReportRequest
from app.config import Settings
from app.database import get_session_factory
from app.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models import BusinessReport
from app.models.base import utc_now
from app.models.enums import ReportPeriodType, ReportStatementKind
from app.models.owner_execution import OwnerExecution
from app.models.owner_execution_enums import OwnerCommandType, OwnerExecutionState
from app.owner.controls import SystemControlService
from app.owner.schemas_commands import FindOpportunitiesResponse
from app.security.redaction import redact_dict

logger = logging.getLogger(__name__)


class ReportListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    period_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    status: str
    key_takeaway: str


class ReportDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    period_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    facts: list[str]
    interpretation: list[str]
    recommendations: list[str]
    advanced_details: dict[str, Any] = Field(default_factory=dict)


class ReportListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReportListItem]
    total: int
    limit: int
    offset: int


class ReportCatalogService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def list_reports(self, *, limit: int = 50, offset: int = 0) -> ReportListView:
        capped = max(1, min(limit, 100))
        off = max(0, offset)
        total = int(
            self._session.scalar(select(func.count()).select_from(BusinessReport)) or 0
        )
        rows = self._session.scalars(
            select(BusinessReport)
            .order_by(BusinessReport.generated_at.desc())
            .offset(off)
            .limit(capped)
        ).all()
        return ReportListView(
            items=[self._to_list_item(r) for r in rows],
            total=total,
            limit=capped,
            offset=off,
        )

    def get_report(self, report_id: UUID) -> ReportDetailView:
        report = self._session.get(BusinessReport, report_id)
        if report is None:
            raise NotFoundError("Report not found", details={"report_id": str(report_id)})
        return self._to_detail(report)

    def generate_async(
        self,
        *,
        period_type: str,
        idempotency_key: str,
        owner_id: str,
        correlation_id: str | None = None,
    ) -> FindOpportunitiesResponse:
        """Queue report generation; returns execution accepted response."""
        try:
            SystemControlService(self._session).assert_ai_operations(actor=owner_id)
        except ForbiddenError as exc:
            raise ForbiddenError(
                "AI operations are paused — cannot generate report.",
                details={"code": "SYSTEM_PAUSED", **(exc.details or {})},
            ) from exc

        try:
            period = ReportPeriodType(period_type.lower())
        except ValueError as exc:
            raise ValidationAppError(
                "Invalid period_type",
                details={"period_type": period_type},
            ) from exc

        existing = self._session.scalar(
            select(OwnerExecution).where(
                OwnerExecution.command_type == OwnerCommandType.GENERATE_REPORT.value,
                OwnerExecution.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return FindOpportunitiesResponse(
                execution_id=existing.id,
                status=existing.status,
                message=existing.result_summary or "Report generation already in progress.",
            )

        execution = OwnerExecution(
            command_type=OwnerCommandType.GENERATE_REPORT.value,
            title="Generating report",
            purpose=f"Generate {period.value} CEO report from database facts",
            status=OwnerExecutionState.QUEUED.value,
            idempotency_key=idempotency_key,
            requested_by=owner_id,
            progress=0,
            completed_steps=0,
            total_steps=2,
            current_activity="Starting",
            request_payload=redact_dict({"period_type": period.value}),
            correlation_id=correlation_id,
            started_at=utc_now(),
        )
        self._session.add(execution)
        self._session.commit()
        execution_id = execution.id
        self._spawn(execution_id, period=period, idempotency_key=idempotency_key)
        return FindOpportunitiesResponse(
            execution_id=execution_id,
            status=OwnerExecutionState.QUEUED.value,
            message="Report generation has started.",
        )

    def _spawn(
        self, execution_id: UUID, *, period: ReportPeriodType, idempotency_key: str
    ) -> None:
        settings = self._settings

        def runner() -> None:
            session = get_session_factory()()
            try:
                row = session.get(OwnerExecution, execution_id)
                if row is None or row.cancel_requested:
                    return
                row.status = OwnerExecutionState.RUNNING.value
                row.current_activity = "Analyzing"
                row.progress = 20
                session.commit()

                agent = ReportAgent(session=session, settings=settings)
                result = agent.run(
                    ReportRequest(
                        period_type=period,
                        idempotency_key=f"owner-report-{idempotency_key}",
                    )
                )
                row = session.get(OwnerExecution, execution_id)
                if row is None:
                    return
                if result.status == "succeeded":
                    row.status = OwnerExecutionState.COMPLETED.value
                    row.current_activity = "Completed"
                    row.progress = 100
                    row.completed_steps = 2
                    row.result_summary = (
                        result.report.title if result.report else "Report generated."
                    )
                    if result.report:
                        row.extra_metadata = {
                            **(row.extra_metadata or {}),
                            "report_id": str(result.report.id),
                        }
                    row.agent_run_id = result.agent_run_id
                else:
                    row.status = OwnerExecutionState.FAILED.value
                    row.failure_message = result.error_message or "Report generation failed"
                    row.current_activity = "Failed"
                row.completed_at = utc_now()
                session.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("owner_generate_report_failed id=%s", execution_id)
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

        threading.Thread(target=runner, name=f"owner-report-{execution_id}", daemon=True).start()

    def _to_list_item(self, report: BusinessReport) -> ReportListItem:
        takeaway = report.summary_text or "No summary available"
        # Prefer first interpretation statement when present
        for section in report.sections or []:
            if not isinstance(section, dict):
                continue
            for stmt in section.get("statements") or []:
                if not isinstance(stmt, dict):
                    continue
                kind = stmt.get("kind")
                if kind in {
                    ReportStatementKind.INTERPRETATION.value,
                    "interpretation",
                    "INTERPRETATION",
                }:
                    takeaway = stmt.get("text") or takeaway
                    break
        return ReportListItem(
            id=report.id,
            title=report.title,
            period_type=report.period_type.value
            if hasattr(report.period_type, "value")
            else str(report.period_type),
            period_start=report.period_start,
            period_end=report.period_end,
            generated_at=report.generated_at,
            status=report.status.value
            if hasattr(report.status, "value")
            else str(report.status),
            key_takeaway=takeaway,
        )

    def _to_detail(self, report: BusinessReport) -> ReportDetailView:
        facts: list[str] = []
        interpretation: list[str] = []
        recommendations: list[str] = []
        for section in report.sections or []:
            if not isinstance(section, dict):
                continue
            for stmt in section.get("statements") or []:
                if not isinstance(stmt, dict):
                    continue
                text = stmt.get("text")
                if not text:
                    continue
                kind = str(stmt.get("kind") or "").lower()
                if "fact" in kind:
                    facts.append(text)
                elif "interpret" in kind:
                    interpretation.append(text)
                elif "recommend" in kind:
                    recommendations.append(text)
        if not facts and report.facts_snapshot:
            facts.append("See advanced details for countable facts snapshot.")
        return ReportDetailView(
            id=report.id,
            title=report.title,
            period_type=report.period_type.value
            if hasattr(report.period_type, "value")
            else str(report.period_type),
            period_start=report.period_start,
            period_end=report.period_end,
            generated_at=report.generated_at,
            facts=facts or ["not available"],
            interpretation=interpretation or ["not yet analyzed"],
            recommendations=recommendations or ["not yet analyzed"],
            advanced_details={
                "report_id": str(report.id),
                "source": report.source,
                "agent_run_id": str(report.agent_run_id) if report.agent_run_id else None,
                "facts_snapshot": report.facts_snapshot,
            },
        )
