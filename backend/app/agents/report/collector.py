"""Collect real database facts for a reporting period — never invent numbers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.calculations import ZERO, as_decimal, gross_profit, quantize_money, roi, sum_amounts
from app.models import (
    Approval,
    Company,
    CompanyAudit,
    CompanyScore,
    CostEntry,
    Customer,
    DeliveryProject,
    FollowUpSequence,
    Lead,
    ManagerDecision,
    ManagerRun,
    OutboundMessage,
    Outreach,
    ProjectTask,
    RevenueEntry,
)
from app.models.enums import (
    ApprovalStatus,
    AuditPriority,
    DeliveryProjectStatus,
    OutboundMessageStatus,
    OutreachStatus,
    ProjectTaskStatus,
    RiskLevel,
    ScoreBand,
)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class ReportFacts:
    """All values are either measured from DB or explicitly marked unavailable."""

    period_start: datetime
    period_end: datetime
    currency: str

    # Goal / progress
    latest_goal: str | None = None
    target_qualified_leads: int | None = None
    measured_qualified_leads: int | None = None
    manager_runs_in_period: int = 0

    companies_researched: int = 0
    companies_total: int = 0
    qualified_leads: int = 0
    audits_in_period: int = 0
    audits_total: int = 0
    high_priority_audits: int = 0

    outreach_drafted: int = 0
    outreach_sent: int = 0
    outreach_failed: int = 0
    outbound_sent: int = 0
    outbound_followups_sent: int = 0

    replies: int = 0
    meetings: int = 0
    customers_converted: int = 0
    customers_total: int = 0

    # Finance — None means no ledger entries (unavailable), Decimal includes 0 if entries exist
    revenue_available: bool = False
    costs_available: bool = False
    total_revenue: Decimal = field(default_factory=lambda: ZERO)
    total_costs: Decimal = field(default_factory=lambda: ZERO)
    gross_profit: Decimal | None = None
    roi: Decimal | None = None
    cost_breakdown: dict[str, Decimal] = field(default_factory=dict)

    pending_approvals: int = 0
    yellow_pending_approvals: int = 0
    red_pending_approvals: int = 0

    delivery_projects_active: int = 0
    delivery_tasks_failed: int = 0
    delivery_tasks_blocked: int = 0
    agent_runs_failed: int = 0
    decisions_failed_or_rejected: int = 0

    best_opportunity_labels: list[str] = field(default_factory=list)
    problem_labels: list[str] = field(default_factory=list)
    worked_labels: list[str] = field(default_factory=list)
    failed_labels: list[str] = field(default_factory=list)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "currency": self.currency,
            "latest_goal": self.latest_goal,
            "target_qualified_leads": self.target_qualified_leads,
            "measured_qualified_leads": self.measured_qualified_leads,
            "manager_runs_in_period": self.manager_runs_in_period,
            "companies_researched": self.companies_researched,
            "companies_total": self.companies_total,
            "qualified_leads": self.qualified_leads,
            "audits_in_period": self.audits_in_period,
            "audits_total": self.audits_total,
            "high_priority_audits": self.high_priority_audits,
            "outreach_drafted": self.outreach_drafted,
            "outreach_sent": self.outreach_sent,
            "outreach_failed": self.outreach_failed,
            "outbound_sent": self.outbound_sent,
            "outbound_followups_sent": self.outbound_followups_sent,
            "replies": self.replies,
            "meetings": self.meetings,
            "customers_converted": self.customers_converted,
            "customers_total": self.customers_total,
            "revenue_available": self.revenue_available,
            "costs_available": self.costs_available,
            "total_revenue": str(self.total_revenue) if self.revenue_available else None,
            "total_costs": str(self.total_costs) if self.costs_available else None,
            "gross_profit": str(self.gross_profit) if self.gross_profit is not None else None,
            "roi": str(self.roi) if self.roi is not None else None,
            "cost_breakdown": {k: str(v) for k, v in self.cost_breakdown.items()},
            "pending_approvals": self.pending_approvals,
            "yellow_pending_approvals": self.yellow_pending_approvals,
            "red_pending_approvals": self.red_pending_approvals,
            "delivery_projects_active": self.delivery_projects_active,
            "delivery_tasks_failed": self.delivery_tasks_failed,
            "delivery_tasks_blocked": self.delivery_tasks_blocked,
            "best_opportunity_labels": self.best_opportunity_labels,
            "problem_labels": self.problem_labels,
            "worked_labels": self.worked_labels,
            "failed_labels": self.failed_labels,
        }


def collect_report_facts(
    session: Session,
    *,
    period_start: datetime,
    period_end: datetime,
    currency: str = "USD",
) -> ReportFacts:
    start = _ensure_aware(period_start)
    end = _ensure_aware(period_end)
    facts = ReportFacts(period_start=start, period_end=end, currency=currency.upper())

    # Manager goal / progress
    runs = list(
        session.scalars(
            select(ManagerRun)
            .where(ManagerRun.started_at >= start, ManagerRun.started_at <= end)
            .order_by(ManagerRun.started_at.desc())
        )
    )
    facts.manager_runs_in_period = len(runs)
    if runs:
        latest = runs[0]
        facts.latest_goal = latest.goal
        facts.target_qualified_leads = latest.target_qualified_leads
        facts.measured_qualified_leads = int(latest.measured_qualified_leads or 0)
    else:
        # Fall back to most recent manager run overall for goal context only
        latest_any = session.scalar(
            select(ManagerRun).order_by(ManagerRun.started_at.desc()).limit(1)
        )
        if latest_any is not None:
            facts.latest_goal = latest_any.goal
            facts.target_qualified_leads = latest_any.target_qualified_leads
            facts.measured_qualified_leads = int(latest_any.measured_qualified_leads or 0)

    facts.companies_total = int(
        session.scalar(select(func.count()).select_from(Company)) or 0
    )
    facts.companies_researched = int(
        session.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.created_at >= start, Company.created_at <= end)
        )
        or 0
    )

    qualified_ids = set(
        session.scalars(
            select(CompanyScore.company_id).where(
                CompanyScore.band.in_([ScoreBand.GOOD.value, ScoreBand.HIGH.value])
            )
        )
    )
    facts.qualified_leads = len(qualified_ids)

    facts.audits_total = int(
        session.scalar(select(func.count()).select_from(CompanyAudit)) or 0
    )
    facts.audits_in_period = int(
        session.scalar(
            select(func.count())
            .select_from(CompanyAudit)
            .where(CompanyAudit.audited_at >= start, CompanyAudit.audited_at <= end)
        )
        or 0
    )
    facts.high_priority_audits = int(
        session.scalar(
            select(func.count())
            .select_from(CompanyAudit)
            .where(
                CompanyAudit.priority.in_(
                    [AuditPriority.HIGH.value, AuditPriority.CRITICAL.value]
                )
            )
        )
        or 0
    )

    facts.outreach_drafted = int(
        session.scalar(
            select(func.count())
            .select_from(Outreach)
            .where(Outreach.drafted_at >= start, Outreach.drafted_at <= end)
        )
        or 0
    )
    facts.outreach_sent = int(
        session.scalar(
            select(func.count())
            .select_from(Outreach)
            .where(
                Outreach.status == OutreachStatus.SENT.value,
                Outreach.sent_at.is_not(None),
                Outreach.sent_at >= start,
                Outreach.sent_at <= end,
            )
        )
        or 0
    )
    facts.outreach_failed = int(
        session.scalar(
            select(func.count())
            .select_from(Outreach)
            .where(
                Outreach.status == OutreachStatus.FAILED.value,
                Outreach.updated_at >= start,
                Outreach.updated_at <= end,
            )
        )
        or 0
    )

    facts.outbound_sent = int(
        session.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(
                OutboundMessage.status == OutboundMessageStatus.SENT.value,
                OutboundMessage.sent_at >= start,
                OutboundMessage.sent_at <= end,
            )
        )
        or 0
    )
    facts.outbound_followups_sent = int(
        session.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(
                OutboundMessage.status == OutboundMessageStatus.SENT.value,
                OutboundMessage.is_followup.is_(True),
                OutboundMessage.sent_at >= start,
                OutboundMessage.sent_at <= end,
            )
        )
        or 0
    )

    facts.replies = int(
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.replied_at.is_not(None),
                Lead.replied_at >= start,
                Lead.replied_at <= end,
            )
        )
        or 0
    )
    facts.meetings = int(
        session.scalar(
            select(func.coalesce(func.sum(FollowUpSequence.meetings_generated), 0)).where(
                FollowUpSequence.response_at >= start,
                FollowUpSequence.response_at <= end,
            )
        )
        or 0
    )
    # Also count meetings recorded without response_at filter via sequences updated in period
    if facts.meetings == 0:
        facts.meetings = int(
            session.scalar(
                select(func.coalesce(func.sum(FollowUpSequence.meetings_generated), 0)).where(
                    FollowUpSequence.updated_at >= start,
                    FollowUpSequence.updated_at <= end,
                    FollowUpSequence.meetings_generated > 0,
                )
            )
            or 0
        )

    facts.customers_total = int(
        session.scalar(select(func.count()).select_from(Customer)) or 0
    )
    facts.customers_converted = int(
        session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.converted_at >= start, Customer.converted_at <= end)
        )
        or 0
    )

    # Finance ledger
    cost_rows = list(
        session.scalars(
            select(CostEntry).where(
                CostEntry.currency == currency.upper(),
                CostEntry.occurred_at >= start,
                CostEntry.occurred_at <= end,
            )
        )
    )
    revenue_rows = list(
        session.scalars(
            select(RevenueEntry).where(
                RevenueEntry.currency == currency.upper(),
                RevenueEntry.occurred_at >= start,
                RevenueEntry.occurred_at <= end,
            )
        )
    )
    facts.costs_available = len(cost_rows) > 0
    facts.revenue_available = len(revenue_rows) > 0
    if facts.costs_available:
        facts.total_costs = sum_amounts([as_decimal(r.amount) for r in cost_rows])
        breakdown: dict[str, Decimal] = {}
        for row in cost_rows:
            key = str(row.category.value if hasattr(row.category, "value") else row.category)
            breakdown[key] = quantize_money(
                breakdown.get(key, ZERO) + as_decimal(row.amount)
            )
        facts.cost_breakdown = breakdown
    if facts.revenue_available:
        facts.total_revenue = sum_amounts([as_decimal(r.amount) for r in revenue_rows])
    if facts.revenue_available or facts.costs_available:
        facts.gross_profit = gross_profit(
            revenue=facts.total_revenue if facts.revenue_available else ZERO,
            costs=facts.total_costs if facts.costs_available else ZERO,
        )
        if facts.costs_available and facts.total_costs != ZERO:
            facts.roi = roi(
                revenue=facts.total_revenue if facts.revenue_available else ZERO,
                costs=facts.total_costs,
            )

    facts.pending_approvals = int(
        session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(Approval.status == ApprovalStatus.PENDING.value)
        )
        or 0
    )
    facts.yellow_pending_approvals = int(
        session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.status == ApprovalStatus.PENDING.value,
                Approval.risk_level == RiskLevel.YELLOW.value,
            )
        )
        or 0
    )
    facts.red_pending_approvals = int(
        session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.status == ApprovalStatus.PENDING.value,
                Approval.risk_level == RiskLevel.RED.value,
            )
        )
        or 0
    )

    facts.delivery_projects_active = int(
        session.scalar(
            select(func.count())
            .select_from(DeliveryProject)
            .where(
                DeliveryProject.status.in_(
                    [
                        DeliveryProjectStatus.ACTIVE.value,
                        DeliveryProjectStatus.DELIVERY.value,
                        DeliveryProjectStatus.VERIFICATION.value,
                    ]
                )
            )
        )
        or 0
    )
    facts.delivery_tasks_failed = int(
        session.scalar(
            select(func.count())
            .select_from(ProjectTask)
            .where(ProjectTask.status == ProjectTaskStatus.FAILED.value)
        )
        or 0
    )
    facts.delivery_tasks_blocked = int(
        session.scalar(
            select(func.count())
            .select_from(ProjectTask)
            .where(ProjectTask.status == ProjectTaskStatus.BLOCKED.value)
        )
        or 0
    )

    # Best opportunities: HIGH band companies with recent/high audits
    high_scores = list(
        session.scalars(
            select(CompanyScore)
            .where(CompanyScore.band == ScoreBand.HIGH.value)
            .order_by(CompanyScore.total_score.desc())
            .limit(5)
        )
    )
    for score in high_scores:
        company = session.get(Company, score.company_id)
        label = company.name if company else str(score.company_id)
        facts.best_opportunity_labels.append(
            f"{label} (score={score.total_score}, band={score.band})"
        )

    # Problems
    if facts.outreach_failed:
        facts.problem_labels.append(f"{facts.outreach_failed} outreach send failure(s)")
    if facts.delivery_tasks_failed:
        facts.problem_labels.append(f"{facts.delivery_tasks_failed} failed delivery task(s)")
    if facts.delivery_tasks_blocked:
        facts.problem_labels.append(f"{facts.delivery_tasks_blocked} blocked delivery task(s)")
    if facts.pending_approvals:
        facts.problem_labels.append(f"{facts.pending_approvals} pending approval(s)")

    # What worked / failed from manager decisions in period
    decisions = list(
        session.scalars(
            select(ManagerDecision).where(
                ManagerDecision.created_at >= start,
                ManagerDecision.created_at <= end,
            )
        )
    )
    for d in decisions:
        dtype = str(d.decision_type.value if hasattr(d.decision_type, "value") else d.decision_type)
        if dtype in {"complete", "execute", "measure"} and d.rationale:
            facts.worked_labels.append(f"{dtype}: {d.rationale[:160]}")
        if dtype in {"reject_invalid", "stop", "skip"} and d.rationale:
            facts.failed_labels.append(f"{dtype}: {d.rationale[:160]}")

    for run in runs:
        if int(run.tasks_succeeded or 0) > 0:
            facts.worked_labels.append(
                f"Manager run succeeded tasks={run.tasks_succeeded} goal={run.goal[:80]!r}"
            )
        if int(run.tasks_failed or 0) > 0:
            facts.failed_labels.append(
                f"Manager run failed tasks={run.tasks_failed} stop={run.stop_reason!r}"
            )

    # Deduplicate labels while preserving order
    facts.worked_labels = _uniq(facts.worked_labels)[:10]
    facts.failed_labels = _uniq(facts.failed_labels)[:10]
    facts.problem_labels = _uniq(facts.problem_labels)[:10]
    facts.best_opportunity_labels = _uniq(facts.best_opportunity_labels)[:5]

    return facts


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
