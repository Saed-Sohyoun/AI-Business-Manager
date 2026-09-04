"""ReportAgent — daily/weekly/monthly CEO reports from real DB data only.

Distinguishes FACT / INTERPRETATION / RECOMMENDATION / UNAVAILABLE.
Never fabricates missing metrics. Never uses AI to invent numbers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.report.collector import collect_report_facts
from app.agents.report.composer import compose_sections
from app.agents.report.schemas import (
    BusinessReportView,
    ReportRequest,
    ReportRunResult,
    ReportSectionView,
    ReportStatementView,
)
from app.approvals.service import ApprovalService
from app.config import Settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.finance.calculations import normalize_currency
from app.models import AgentRun, BusinessReport
from app.models.base import utc_now
from app.models.enums import (
    AgentRunStatus,
    BusinessReportStatus,
    ReportPeriodType,
    ReportStatementKind,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "report"
TASK_TYPE = "generate"
ACTION_GENERATE = "report.generate"


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_period(
    period_type: ReportPeriodType,
    *,
    as_of: datetime | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Derive an inclusive reporting window.

    Daily: [day 00:00, day 23:59:59.999999]
    Weekly: last 7 days ending as_of
    Monthly: calendar month containing as_of
    Explicit start/end override when both provided.
    """
    if period_start is not None and period_end is not None:
        start = _ensure_aware(period_start)
        end = _ensure_aware(period_end)
        if end < start:
            raise ValidationAppError("period_end must be >= period_start")
        return start, end

    clock = _ensure_aware(as_of or utc_now())
    if period_type == ReportPeriodType.DAILY:
        start = datetime(clock.year, clock.month, clock.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
        return start, end
    if period_type == ReportPeriodType.WEEKLY:
        end = clock
        start = end - timedelta(days=7)
        return start, end
    if period_type == ReportPeriodType.MONTHLY:
        start = datetime(clock.year, clock.month, 1, tzinfo=timezone.utc)
        if clock.month == 12:
            next_month = datetime(clock.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month = datetime(clock.year, clock.month + 1, 1, tzinfo=timezone.utc)
        end = next_month - timedelta(microseconds=1)
        return start, end
    raise ValidationAppError(f"Unsupported period_type: {period_type}")


class ReportAgent:
    """Generate and store CEO reports from database facts only."""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._approvals = approval_service or ApprovalService(session, settings)

    def run(self, request: ReportRequest) -> ReportRunResult:
        logs: list[str] = []
        if request.idempotency_key:
            existing = self._find_run(request.idempotency_key)
            if existing is not None:
                return self._result_from_existing(existing, logs=["idempotent_replay"])

        try:
            self._approvals.assert_executable(ACTION_GENERATE)
        except ForbiddenError as exc:
            return ReportRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=f"approval_gate: {exc.message}",
                logs=["generate_blocked_by_gate"],
            )

        try:
            start, end = resolve_period(
                request.period_type,
                as_of=request.as_of,
                period_start=request.period_start,
                period_end=request.period_end,
            )
        except ValidationAppError as exc:
            return ReportRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=exc.message,
                logs=["invalid_period"],
            )

        currency = normalize_currency(request.currency)
        key = request.idempotency_key or (
            f"report:{request.period_type.value}:{currency}:"
            f"{start.isoformat()}:{end.isoformat()}"
        )

        existing_report = self._session.scalar(
            select(BusinessReport).where(BusinessReport.idempotency_key == key)
        )
        if existing_report is not None:
            return ReportRunResult(
                agent_run_id=existing_report.agent_run_id or UUID(int=0),
                status="succeeded",
                report=self._view(existing_report),
                idempotent_replay=True,
                logs=["idempotent_report_replay"],
            )

        agent_run = AgentRun(
            agent_name=AGENT_NAME,
            task_type=TASK_TYPE,
            status=AgentRunStatus.RUNNING,
            input_summary=(
                f"period={request.period_type.value} "
                f"{start.isoformat()}..{end.isoformat()} currency={currency}"
            ),
            idempotency_key=key if request.idempotency_key else None,
            estimated_cost=Decimal("0"),
            extra_metadata={
                "period_type": request.period_type.value,
                **(request.metadata or {}),
            },
        )
        try:
            self._session.add(agent_run)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            return ReportRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=f"database_failure: {type(exc).__name__}",
                logs=["database_failure_on_run_create"],
            )

        try:
            report = self.generate(
                period_type=request.period_type,
                period_start=start,
                period_end=end,
                currency=currency,
                idempotency_key=key,
                agent_run_id=agent_run.id,
                commit=False,
            )
            agent_run.status = AgentRunStatus.SUCCEEDED
            agent_run.completed_at = utc_now()
            agent_run.output_summary = f"report_id={report.id} sections={len(report.sections)}"
            # Ensure agent run shares idempotency when auto-key used
            if agent_run.idempotency_key is None:
                agent_run.idempotency_key = f"agent-run:{key}"
            self._session.commit()
            logs.append("report_generated")
            # Best-effort owner alert for daily CEO reports only.
            if request.period_type.value == "daily":
                try:
                    from app.services.notification_service import build_notification_service

                    build_notification_service(
                        self._session, self._settings
                    ).notify_daily_ceo_report(
                        report_id=report.id,
                        title=report.title,
                        summary=report.summary_text,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("report_notification_skipped", exc_info=True)
            return ReportRunResult(
                agent_run_id=agent_run.id,
                status="succeeded",
                report=self._view(report),
                logs=logs,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ReportAgent.run failed")
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = f"{type(exc).__name__}: {exc}"
            agent_run.completed_at = utc_now()
            self._session.commit()
            return ReportRunResult(
                agent_run_id=agent_run.id,
                status="failed",
                error_message=agent_run.error_message,
                logs=logs + ["unhandled_error"],
            )

    def generate(
        self,
        *,
        period_type: ReportPeriodType,
        period_start: datetime,
        period_end: datetime,
        currency: str = "USD",
        idempotency_key: str,
        agent_run_id: UUID | None = None,
        commit: bool = True,
    ) -> BusinessReport:
        self._approvals.assert_executable(ACTION_GENERATE)

        existing = self._session.scalar(
            select(BusinessReport).where(BusinessReport.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        facts = collect_report_facts(
            self._session,
            period_start=period_start,
            period_end=period_end,
            currency=currency,
        )
        sections = compose_sections(facts)
        title = self._title(period_type, period_start, period_end)

        report = BusinessReport(
            period_type=period_type,
            period_start=_ensure_aware(period_start),
            period_end=_ensure_aware(period_end),
            title=title,
            status=BusinessReportStatus.GENERATED,
            currency=normalize_currency(currency),
            source="report_agent",
            generated_at=utc_now(),
            idempotency_key=idempotency_key,
            sections=sections,
            facts_snapshot=facts.to_snapshot(),
            agent_run_id=agent_run_id,
            summary_text=self._summary(sections),
            extra_metadata={
                "fabrication": False,
                "ai_used_for_numbers": False,
                "statement_kinds": ["fact", "interpretation", "recommendation", "unavailable"],
            },
        )
        try:
            with self._session.begin_nested():
                self._session.add(report)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(BusinessReport).where(
                    BusinessReport.idempotency_key == idempotency_key
                )
            )
            if existing is None:
                raise
            return existing

        if commit:
            self._session.commit()
        else:
            self._session.flush()
        logger.info(
            "business_report_generated id=%s period=%s sections=%s",
            report.id,
            period_type.value,
            len(sections),
        )
        return report

    def get_report(self, report_id: UUID) -> BusinessReportView | None:
        report = self._session.get(BusinessReport, report_id)
        if report is None:
            return None
        return self._view(report)

    def _title(
        self,
        period_type: ReportPeriodType,
        start: datetime,
        end: datetime,
    ) -> str:
        label = period_type.value.capitalize()
        return f"{label} CEO Report ({start.date().isoformat()} → {end.date().isoformat()})"

    def _summary(self, sections: list[dict]) -> str:
        lines: list[str] = []
        for section in sections:
            facts = [
                s["text"]
                for s in section.get("statements", [])
                if s.get("kind") == ReportStatementKind.FACT.value
            ]
            if facts:
                lines.append(f"{section['title']}: {facts[0]}")
        return "\n".join(lines[:20])

    def _view(self, report: BusinessReport) -> BusinessReportView:
        sections: list[ReportSectionView] = []
        for raw in report.sections or []:
            statements = [
                ReportStatementView(
                    kind=ReportStatementKind(s["kind"]),
                    text=s["text"],
                    value=s.get("value"),
                    available=bool(s.get("available", True)),
                )
                for s in raw.get("statements", [])
            ]
            sections.append(
                ReportSectionView(
                    section_id=raw["section_id"],
                    title=raw["title"],
                    order=int(raw.get("order", 0)),
                    statements=statements,
                )
            )
        return BusinessReportView(
            id=report.id,
            period_type=(
                report.period_type
                if isinstance(report.period_type, ReportPeriodType)
                else ReportPeriodType(report.period_type)
            ),
            period_start=report.period_start,
            period_end=report.period_end,
            title=report.title,
            currency=report.currency,
            sections=sections,
            facts_snapshot=dict(report.facts_snapshot or {}),
            generated_at=report.generated_at,
            source=report.source,
        )

    def _find_run(self, key: str) -> AgentRun | None:
        return self._session.scalar(
            select(AgentRun).where(
                AgentRun.idempotency_key == key,
                AgentRun.agent_name == AGENT_NAME,
            )
        )

    def _result_from_existing(self, run: AgentRun, *, logs: list[str]) -> ReportRunResult:
        report = self._session.scalar(
            select(BusinessReport).where(BusinessReport.agent_run_id == run.id).limit(1)
        )
        if report is None:
            report = self._session.scalar(
                select(BusinessReport).where(
                    BusinessReport.idempotency_key == (run.idempotency_key or "")
                )
            )
        if report is None or run.status != AgentRunStatus.SUCCEEDED:
            return ReportRunResult(
                agent_run_id=run.id,
                status="failed" if run.status == AgentRunStatus.FAILED else "succeeded",
                estimated_cost=run.estimated_cost or Decimal("0"),
                idempotent_replay=True,
                error_message=run.error_message,
                logs=logs,
            )
        return ReportRunResult(
            agent_run_id=run.id,
            status="succeeded",
            report=self._view(report),
            estimated_cost=run.estimated_cost or Decimal("0"),
            idempotent_replay=True,
            logs=logs,
        )
