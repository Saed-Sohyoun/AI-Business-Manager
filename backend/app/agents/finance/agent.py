"""FinanceAgent — record ledger entries and compute deterministic metrics.

Never fabricates financial numbers. Never uses float.
Money-moving actions (transfer/payment) remain RED / human-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.finance.schemas import (
    CostBreakdown,
    CostRecordRequest,
    FinanceCalculateRequest,
    FinanceRunResult,
    FinancialMetricView,
    RevenueRecordRequest,
)
from app.approvals.service import ApprovalService
from app.config import Settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.finance.calculations import (
    ZERO,
    as_decimal,
    cost_per_unit,
    customer_acquisition_cost,
    gross_profit,
    mrr_from_recurring,
    normalize_currency,
    quantize_money,
    roi,
    sum_amounts,
)
from app.models import AgentRun, CostEntry, DailyMetric, FinancialMetric, RevenueEntry
from app.models.base import utc_now
from app.models.enums import AgentRunStatus, CostCategory, RevenueType

logger = logging.getLogger(__name__)

AGENT_NAME = "finance"
TASK_TYPE = "calculate_metrics"

ACTION_RECORD_COST = "finance.record_cost"
ACTION_RECORD_REVENUE = "finance.record_revenue"
ACTION_CALCULATE = "finance.calculate_metrics"
ACTION_REPORT = "finance.report"


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_category(value: CostCategory | str) -> CostCategory:
    if isinstance(value, CostCategory):
        return value
    return CostCategory(value)


class FinanceAgent:
    """Ledger + deterministic financial reporting. No autonomous money movement."""

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

    # ----------------------------------------------------------------- run
    def run(self, request: FinanceCalculateRequest) -> FinanceRunResult:
        logs: list[str] = []
        key = request.idempotency_key
        if key:
            existing = self._find_run(key)
            if existing is not None:
                return self._result_from_existing(existing, logs=["idempotent_replay"])

        try:
            self._approvals.assert_executable(ACTION_CALCULATE)
        except ForbiddenError as exc:
            return FinanceRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=f"approval_gate: {exc.message}",
                logs=["calculate_blocked_by_gate"],
            )

        if _ensure_aware(request.period_end) < _ensure_aware(request.period_start):
            return FinanceRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message="period_end_before_period_start",
                logs=["invalid_period"],
            )

        agent_run = AgentRun(
            agent_name=AGENT_NAME,
            task_type=TASK_TYPE,
            status=AgentRunStatus.RUNNING,
            input_summary=(
                f"currency={request.currency} "
                f"period={request.period_start.isoformat()}..{request.period_end.isoformat()}"
            ),
            idempotency_key=key,
            estimated_cost=Decimal("0"),
            extra_metadata=dict(request.metadata or {}),
        )
        try:
            self._session.add(agent_run)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            return FinanceRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=f"database_failure: {type(exc).__name__}",
                logs=["database_failure_on_run_create"],
            )

        try:
            metric = self.calculate_metrics(
                request,
                agent_run_id=agent_run.id,
                commit=False,
            )
            agent_run.status = AgentRunStatus.SUCCEEDED
            agent_run.completed_at = utc_now()
            agent_run.output_summary = (
                f"revenue={metric.total_revenue} costs={metric.total_costs} "
                f"profit={metric.gross_profit} roi={metric.roi}"
            )
            self._session.commit()
            logs.append("metrics_calculated")
            return FinanceRunResult(
                agent_run_id=agent_run.id,
                status="succeeded",
                metric=self._metric_view(metric),
                logs=logs,
            )
        except (ValidationAppError, ForbiddenError, ValueError, TypeError) as exc:
            message = getattr(exc, "message", str(exc))
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = message
            agent_run.completed_at = utc_now()
            self._session.commit()
            return FinanceRunResult(
                agent_run_id=agent_run.id,
                status="failed",
                error_message=message,
                logs=logs + ["calculation_failed"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("FinanceAgent.run failed")
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = f"{type(exc).__name__}: {exc}"
            agent_run.completed_at = utc_now()
            self._session.commit()
            return FinanceRunResult(
                agent_run_id=agent_run.id,
                status="failed",
                error_message=agent_run.error_message,
                logs=logs + ["unhandled_error"],
            )

    # --------------------------------------------------------------- record
    def record_cost(self, request: CostRecordRequest, *, commit: bool = True) -> CostEntry:
        self._approvals.assert_executable(ACTION_RECORD_COST)

        amount = quantize_money(request.amount)
        from app.pilot.budget import BudgetGuard

        BudgetGuard(self._session, self._settings).assert_expense_allowed(amount)

        existing = self._session.scalar(
            select(CostEntry).where(CostEntry.idempotency_key == request.idempotency_key)
        )
        if existing is not None:
            return existing

        entry = CostEntry(
            amount=amount,
            currency=normalize_currency(request.currency),
            category=request.category,
            source=request.source.strip(),
            transaction_reference=request.transaction_reference,
            occurred_at=_ensure_aware(request.occurred_at or utc_now()),
            description=request.description,
            idempotency_key=request.idempotency_key,
            extra_metadata=dict(request.metadata or {}),
        )
        try:
            with self._session.begin_nested():
                self._session.add(entry)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(CostEntry).where(CostEntry.idempotency_key == request.idempotency_key)
            )
            if existing is None:
                raise
            return existing

        self._bump_daily_costs(amount, entry.occurred_at.date())
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        logger.info(
            "cost_recorded id=%s category=%s amount=%s %s",
            entry.id,
            entry.category,
            entry.amount,
            entry.currency,
        )
        return entry

    def record_revenue(
        self,
        request: RevenueRecordRequest,
        *,
        commit: bool = True,
    ) -> RevenueEntry:
        self._approvals.assert_executable(ACTION_RECORD_REVENUE)

        existing = self._session.scalar(
            select(RevenueEntry).where(
                RevenueEntry.idempotency_key == request.idempotency_key
            )
        )
        if existing is not None:
            return existing

        amount = quantize_money(request.amount)
        is_recurring = bool(request.is_recurring) or request.revenue_type == RevenueType.SUBSCRIPTION
        entry = RevenueEntry(
            amount=amount,
            currency=normalize_currency(request.currency),
            revenue_type=request.revenue_type,
            is_recurring=is_recurring,
            source=request.source.strip(),
            transaction_reference=request.transaction_reference,
            customer_id=request.customer_id,
            occurred_at=_ensure_aware(request.occurred_at or utc_now()),
            description=request.description,
            idempotency_key=request.idempotency_key,
            extra_metadata=dict(request.metadata or {}),
        )
        try:
            with self._session.begin_nested():
                self._session.add(entry)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(RevenueEntry).where(
                    RevenueEntry.idempotency_key == request.idempotency_key
                )
            )
            if existing is None:
                raise
            return existing

        self._bump_daily_revenue(amount, entry.occurred_at.date())
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        logger.info(
            "revenue_recorded id=%s type=%s amount=%s %s",
            entry.id,
            entry.revenue_type,
            entry.amount,
            entry.currency,
        )
        return entry

    # ------------------------------------------------------------ calculate
    def calculate_metrics(
        self,
        request: FinanceCalculateRequest,
        *,
        agent_run_id: UUID | None = None,
        commit: bool = True,
    ) -> FinancialMetric:
        self._approvals.assert_executable(ACTION_CALCULATE)

        currency = normalize_currency(request.currency)
        start = _ensure_aware(request.period_start)
        end = _ensure_aware(request.period_end)
        if end < start:
            raise ValidationAppError("period_end must be >= period_start")

        key = request.idempotency_key or (
            f"finance-metric:{currency}:{start.isoformat()}:{end.isoformat()}"
            f":L{request.lead_count}:Q{request.qualified_lead_count}:C{request.customer_count}"
        )
        existing = self._session.scalar(
            select(FinancialMetric).where(FinancialMetric.idempotency_key == key)
        )
        if existing is not None:
            return existing

        costs = list(
            self._session.scalars(
                select(CostEntry).where(
                    CostEntry.currency == currency,
                    CostEntry.occurred_at >= start,
                    CostEntry.occurred_at <= end,
                )
            )
        )
        revenues = list(
            self._session.scalars(
                select(RevenueEntry).where(
                    RevenueEntry.currency == currency,
                    RevenueEntry.occurred_at >= start,
                    RevenueEntry.occurred_at <= end,
                )
            )
        )

        breakdown = {cat: ZERO for cat in CostCategory}
        for row in costs:
            cat = _as_category(row.category)
            breakdown[cat] = quantize_money(breakdown[cat] + as_decimal(row.amount))

        total_costs = sum_amounts([as_decimal(row.amount) for row in costs])
        total_revenue = sum_amounts([as_decimal(row.amount) for row in revenues])
        profit = gross_profit(revenue=total_revenue, costs=total_costs)
        recurring = [
            as_decimal(row.amount)
            for row in revenues
            if row.is_recurring or _as_revenue_type(row.revenue_type) == RevenueType.SUBSCRIPTION
        ]
        mrr = mrr_from_recurring(recurring)
        delivery = breakdown[CostCategory.DELIVERY]

        cpl = cost_per_unit(total_costs=total_costs, unit_count=request.lead_count)
        cpql = cost_per_unit(
            total_costs=total_costs,
            unit_count=request.qualified_lead_count,
        )
        cac = customer_acquisition_cost(
            total_costs=total_costs,
            customer_count=request.customer_count,
        )
        roi_value = roi(revenue=total_revenue, costs=total_costs)

        metric = FinancialMetric(
            period_start=start,
            period_end=end,
            currency=currency,
            calculated_at=utc_now(),
            source="finance_agent",
            idempotency_key=key,
            total_revenue=total_revenue,
            total_costs=total_costs,
            gross_profit=profit,
            mrr=mrr,
            ai_costs=breakdown[CostCategory.AI],
            search_costs=breakdown[CostCategory.SEARCH],
            email_costs=breakdown[CostCategory.EMAIL],
            browser_costs=breakdown[CostCategory.BROWSER],
            delivery_costs=delivery,
            other_operational_costs=breakdown[CostCategory.OTHER_OPERATIONAL],
            lead_count=request.lead_count,
            qualified_lead_count=request.qualified_lead_count,
            customer_count=request.customer_count,
            cost_per_lead=cpl,
            cost_per_qualified_lead=cpql,
            customer_acquisition_cost=cac,
            delivery_cost=delivery,
            roi=roi_value,
            agent_run_id=agent_run_id,
            extra_metadata={
                "cost_entry_count": len(costs),
                "revenue_entry_count": len(revenues),
                "calculation": "deterministic_decimal",
                **(request.metadata or {}),
            },
        )
        try:
            with self._session.begin_nested():
                self._session.add(metric)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(FinancialMetric).where(FinancialMetric.idempotency_key == key)
            )
            if existing is None:
                raise
            return existing

        # Sync DailyMetric money fields for the period end date (same currency assumed USD daily)
        self._sync_daily_metric_money(
            metric_date=end.date(),
            revenue=total_revenue,
            costs=total_costs,
            profit=profit,
        )

        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return metric

    # --------------------------------------------------------------- helpers
    def _metric_view(self, metric: FinancialMetric) -> FinancialMetricView:
        return FinancialMetricView(
            id=metric.id,
            period_start=metric.period_start,
            period_end=metric.period_end,
            currency=metric.currency,
            total_revenue=as_decimal(metric.total_revenue),
            total_costs=as_decimal(metric.total_costs),
            gross_profit=as_decimal(metric.gross_profit),
            mrr=as_decimal(metric.mrr),
            cost_breakdown=CostBreakdown(
                ai=as_decimal(metric.ai_costs),
                search=as_decimal(metric.search_costs),
                email=as_decimal(metric.email_costs),
                browser=as_decimal(metric.browser_costs),
                delivery=as_decimal(metric.delivery_costs),
                other_operational=as_decimal(metric.other_operational_costs),
            ),
            cost_per_lead=as_decimal(metric.cost_per_lead) if metric.cost_per_lead is not None else None,
            cost_per_qualified_lead=(
                as_decimal(metric.cost_per_qualified_lead)
                if metric.cost_per_qualified_lead is not None
                else None
            ),
            customer_acquisition_cost=(
                as_decimal(metric.customer_acquisition_cost)
                if metric.customer_acquisition_cost is not None
                else None
            ),
            delivery_cost=as_decimal(metric.delivery_cost),
            roi=as_decimal(metric.roi) if metric.roi is not None else None,
            lead_count=metric.lead_count,
            qualified_lead_count=metric.qualified_lead_count,
            customer_count=metric.customer_count,
            calculated_at=metric.calculated_at,
            source=metric.source,
        )

    def _bump_daily_costs(self, amount: Decimal, metric_date) -> None:
        row = self._daily(metric_date)
        row.costs = quantize_money(as_decimal(row.costs or ZERO) + amount)
        row.profit = gross_profit(
            revenue=as_decimal(row.revenue or ZERO),
            costs=as_decimal(row.costs),
        )

    def _bump_daily_revenue(self, amount: Decimal, metric_date) -> None:
        row = self._daily(metric_date)
        row.revenue = quantize_money(as_decimal(row.revenue or ZERO) + amount)
        row.profit = gross_profit(
            revenue=as_decimal(row.revenue),
            costs=as_decimal(row.costs or ZERO),
        )

    def _sync_daily_metric_money(
        self,
        *,
        metric_date,
        revenue: Decimal,
        costs: Decimal,
        profit: Decimal,
    ) -> None:
        # DailyMetric uses Numeric(14,2) — quantize to cents for that snapshot only.
        cent = Decimal("0.01")
        row = self._daily(metric_date)
        row.revenue = as_decimal(revenue).quantize(cent)
        row.costs = as_decimal(costs).quantize(cent)
        row.profit = as_decimal(profit).quantize(cent)

    def _daily(self, metric_date) -> DailyMetric:
        row = self._session.scalar(
            select(DailyMetric).where(DailyMetric.metric_date == metric_date)
        )
        if row is None:
            row = DailyMetric(metric_date=metric_date)
            self._session.add(row)
            self._session.flush()
        return row

    def _find_run(self, key: str) -> AgentRun | None:
        return self._session.scalar(
            select(AgentRun).where(
                AgentRun.idempotency_key == key,
                AgentRun.agent_name == AGENT_NAME,
            )
        )

    def _result_from_existing(self, run: AgentRun, *, logs: list[str]) -> FinanceRunResult:
        metric = self._session.scalar(
            select(FinancialMetric).where(FinancialMetric.agent_run_id == run.id).limit(1)
        )
        if metric is None or run.status != AgentRunStatus.SUCCEEDED:
            return FinanceRunResult(
                agent_run_id=run.id,
                status="failed" if run.status == AgentRunStatus.FAILED else "succeeded",
                estimated_cost=run.estimated_cost or Decimal("0"),
                idempotent_replay=True,
                error_message=run.error_message,
                logs=logs,
            )
        return FinanceRunResult(
            agent_run_id=run.id,
            status="succeeded",
            metric=self._metric_view(metric),
            estimated_cost=run.estimated_cost or Decimal("0"),
            idempotent_replay=True,
            logs=logs,
        )


def _as_revenue_type(value: RevenueType | str) -> RevenueType:
    if isinstance(value, RevenueType):
        return value
    return RevenueType(value)
