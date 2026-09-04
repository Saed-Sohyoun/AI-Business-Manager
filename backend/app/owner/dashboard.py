"""Owner dashboard summary — database-derived values only."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AgentRun,
    Approval,
    Company,
    CostEntry,
    Customer,
    Lead,
    ManagerRun,
    ManagerTask,
    Outreach,
    RevenueEntry,
)
from app.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    LeadStatus,
    ManagerRunStatus,
    ManagerTaskStatus,
    OutreachStatus,
)
from app.models.owner_alert import OwnerAlert
from app.models.system_mode import AlertPriority
from app.owner.schemas import (
    DashboardActivityEntry,
    DashboardAttention,
    DashboardGoal,
    DashboardMoney,
    DashboardPipeline,
    DashboardSummaryView,
    DashboardTeamActivity,
)
from app.finance.calculations import as_decimal, gross_profit, quantize_money


class DashboardService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def summary(self) -> DashboardSummaryView:
        revenue = self._sum_revenue()
        costs = self._sum_costs()
        profit = quantize_money(gross_profit(revenue=revenue, costs=costs))
        companies = self._count(Company)
        qualified = int(
            self._session.scalar(
                select(func.count()).select_from(Lead).where(
                    Lead.status.in_(
                        [LeadStatus.QUALIFIED.value, LeadStatus.CONTACTED.value]
                    )
                )
            )
            or 0
        )
        opportunities = int(
            self._session.scalar(
                select(func.count())
                .select_from(Outreach)
                .where(
                    Outreach.status.in_(
                        [
                            OutreachStatus.PENDING_APPROVAL.value,
                            OutreachStatus.APPROVED.value,
                            OutreachStatus.SENT.value,
                        ]
                    )
                )
            )
            or 0
        )
        customers = self._count(Customer)
        pending = int(
            self._session.scalar(
                select(func.count())
                .select_from(Approval)
                .where(Approval.status == ApprovalStatus.PENDING.value)
            )
            or 0
        )
        urgent = int(
            self._session.scalar(
                select(func.count())
                .select_from(OwnerAlert)
                .where(
                    OwnerAlert.acknowledged.is_(False),
                    OwnerAlert.priority.in_(
                        [AlertPriority.URGENT.value, AlertPriority.CRITICAL.value]
                    ),
                )
            )
            or 0
        )
        blocked = int(
            self._session.scalar(
                select(func.count())
                .select_from(ManagerTask)
                .where(
                    ManagerTask.status.in_(
                        [
                            ManagerTaskStatus.AWAITING_APPROVAL.value,
                            ManagerTaskStatus.FAILED.value,
                            ManagerTaskStatus.TIMED_OUT.value,
                        ]
                    )
                )
            )
            or 0
        )

        goal_title, progress, target = self._current_goal()
        return DashboardSummaryView(
            current_goal=DashboardGoal(
                title=goal_title,
                progress=progress,
                target=target,
                unit="tasks",
            ),
            money=DashboardMoney(
                revenue=str(quantize_money(revenue)),
                costs=str(quantize_money(costs)),
                profit=str(profit),
                currency="EUR",
            ),
            pipeline=DashboardPipeline(
                companies=companies,
                qualified_leads=qualified,
                opportunities=opportunities,
                customers=customers,
            ),
            attention=DashboardAttention(
                pending_approvals=pending,
                urgent_alerts=urgent,
                blocked_work=blocked,
            ),
            team_activity=self._team_activity(),
            recent_activity=self._recent_activity(),
        )

    def _sum_revenue(self) -> Decimal:
        total = self._session.scalar(select(func.coalesce(func.sum(RevenueEntry.amount), 0)))
        return as_decimal(total or 0)

    def _sum_costs(self) -> Decimal:
        total = self._session.scalar(select(func.coalesce(func.sum(CostEntry.amount), 0)))
        return as_decimal(total or 0)

    def _count(self, model) -> int:
        return int(self._session.scalar(select(func.count()).select_from(model)) or 0)

    def _current_goal(self) -> tuple[str, float, float]:
        active_statuses = [
            ManagerRunStatus.PLANNING.value,
            ManagerRunStatus.AWAITING_APPROVAL.value,
        ]
        # Include executing / running variants if present on the enum
        for name in ("EXECUTING", "RUNNING", "IN_PROGRESS", "ACTIVE"):
            member = getattr(ManagerRunStatus, name, None)
            if member is not None:
                active_statuses.append(member.value)
        run = self._session.scalar(
            select(ManagerRun)
            .where(ManagerRun.status.in_(active_statuses))
            .order_by(ManagerRun.created_at.desc())
            .limit(1)
        )
        if run is None:
            return ("No active goal", 0.0, 0.0)
        tasks = self._session.scalars(
            select(ManagerTask).where(ManagerTask.manager_run_id == run.id)
        ).all()
        total = len(tasks)
        done = sum(
            1
            for t in tasks
            if (
                t.status.value if hasattr(t.status, "value") else str(t.status)
            )
            in {
                ManagerTaskStatus.SUCCEEDED.value,
                ManagerTaskStatus.SKIPPED.value,
            }
        )
        return (run.goal[:200], float(done), float(total))

    def _team_activity(self) -> DashboardTeamActivity:
        def _running(agent: str) -> int:
            return int(
                self._session.scalar(
                    select(func.count())
                    .select_from(AgentRun)
                    .where(
                        AgentRun.agent_name == agent,
                        AgentRun.status.in_(
                            [
                                AgentRunStatus.RUNNING.value,
                                AgentRunStatus.PENDING.value,
                            ]
                        ),
                    )
                )
                or 0
            )

        waiting = int(
            self._session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.status == AgentRunStatus.AWAITING_APPROVAL.value)
            )
            or 0
        )
        return DashboardTeamActivity(
            researching=_running("research"),
            auditing=_running("audit"),
            drafting=_running("sales"),
            delivering=_running("delivery"),
            waiting=waiting,
        )

    def _recent_activity(self) -> list[DashboardActivityEntry]:
        rows = self._session.scalars(
            select(AgentRun).order_by(AgentRun.started_at.desc()).limit(10)
        ).all()
        entries: list[DashboardActivityEntry] = []
        for row in rows:
            status = row.status.value if hasattr(row.status, "value") else str(row.status)
            entries.append(
                DashboardActivityEntry(
                    title=f"{row.agent_name}: {row.task_type} ({status})",
                    at=row.started_at,
                    kind=row.agent_name,
                )
            )
        return entries
