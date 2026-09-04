"""Owner system status aggregation."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AgentRun, Approval
from app.models.enums import AgentRunStatus, ApprovalStatus
from app.models.security_event import SecurityEvent
from app.owner.controls import SystemControlService
from app.owner.schemas import SystemStatusView
from app.providers.circuit_breaker import all_circuit_snapshots
from app.security import daily_cost_total


class SystemStatusService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._controls = SystemControlService(session)

    def status(self) -> SystemStatusView:
        state = self._controls.get_or_create()
        active_runs = int(
            self._session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(
                    AgentRun.status.in_(
                        [
                            AgentRunStatus.RUNNING.value,
                            AgentRunStatus.PENDING.value,
                            AgentRunStatus.AWAITING_APPROVAL.value,
                        ]
                    )
                )
            )
            or 0
        )
        pending = int(
            self._session.scalar(
                select(func.count())
                .select_from(Approval)
                .where(Approval.status == ApprovalStatus.PENDING.value)
            )
            or 0
        )
        recent_failures = int(
            self._session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.status == AgentRunStatus.FAILED.value)
            )
            or 0
        )
        security_alerts = int(
            self._session.scalar(select(func.count()).select_from(SecurityEvent)) or 0
        )
        last_ok = self._session.scalar(
            select(AgentRun.completed_at)
            .where(
                AgentRun.status == AgentRunStatus.SUCCEEDED.value,
                AgentRun.completed_at.is_not(None),
            )
            .order_by(AgentRun.completed_at.desc())
            .limit(1)
        )
        spent = daily_cost_total(self._session)
        circuits = all_circuit_snapshots()
        # Owner-friendly labels — no vendor names in primary health
        label_map = {
            "search": "Research service",
            "tavily": "Research service",
            "ai": "AI service",
            "openai": "AI service",
            "email": "Email service",
            "browser": "Browser service",
        }
        health: list[dict] = []
        for snap in circuits:
            name = snap.get("name") or "service"
            state_name = snap.get("state") or "closed"
            label = label_map.get(name, name)
            if state_name == "open":
                level = "Unavailable"
            elif state_name == "half_open":
                level = "Degraded"
            else:
                level = "Healthy"
            health.append(
                {
                    "service": label,
                    "status": level,
                    "advanced": {"provider": name, "circuit": state_name},
                }
            )
        if any(h["status"] == "Unavailable" for h in health):
            summary = "A service is temporarily unavailable"
        elif any(h["status"] == "Degraded" for h in health):
            summary = "Research temporarily degraded"
        else:
            summary = "System operational"
        return SystemStatusView(
            system_mode=state.system_mode,
            ai_operations=bool(state.ai_operations_enabled),
            outbound=bool(state.outbound_enabled),
            spending=bool(state.spending_enabled),
            browser_automation=bool(state.browser_automation_enabled),
            pilot_mode=self._settings.is_pilot_mode,
            production_locked=not self._settings.allow_production_mode,
            active_runs=active_runs,
            pending_approvals=pending,
            recent_failures=recent_failures,
            security_alerts=security_alerts,
            current_budget_usage=str(spent),
            budget_limit=str(self._settings.daily_budget_limit),
            currency="EUR",
            last_successful_run=last_ok,
            safe_mode_reason=state.safe_mode_reason,
            pause_reason=state.pause_reason,
            provider_health=health,
            health_summary=summary,
        )
