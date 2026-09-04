"""Active work presentation for the owner control plane."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, ManagerTask
from app.models.base import utc_now
from app.models.enums import AgentRunStatus, ManagerTaskStatus
from app.owner.schemas import ActiveWorkAdvanced, ActiveWorkItem, ActiveWorkListView

_TITLE_MAP = {
    "research": "Finding potential customers",
    "audit": "Reviewing business opportunities",
    "sales": "Preparing outreach",
    "delivery": "Delivering work",
    "finance": "Updating financial records",
    "manager": "Coordinating the team",
    "scoring": "Scoring leads",
    "report": "Preparing a report",
}

_ACTIVE_AGENT = frozenset(
    {
        AgentRunStatus.PENDING.value,
        AgentRunStatus.RUNNING.value,
        AgentRunStatus.AWAITING_APPROVAL.value,
    }
)

_ACTIVE_TASK = frozenset(
    {
        ManagerTaskStatus.PENDING.value,
        ManagerTaskStatus.READY.value,
        ManagerTaskStatus.RUNNING.value,
        ManagerTaskStatus.RETRYING.value,
        ManagerTaskStatus.AWAITING_APPROVAL.value,
    }
)


class ActiveWorkService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active(self, *, limit: int = 50) -> ActiveWorkListView:
        capped = max(1, min(limit, 100))
        runs = self._session.scalars(
            select(AgentRun)
            .where(AgentRun.status.in_(list(_ACTIVE_AGENT)))
            .order_by(AgentRun.started_at.desc())
            .limit(capped)
        ).all()
        items: list[ActiveWorkItem] = []
        for run in runs:
            status_raw = run.status.value if hasattr(run.status, "value") else str(run.status)
            needs = status_raw == AgentRunStatus.AWAITING_APPROVAL.value
            started = run.started_at
            items.append(
                ActiveWorkItem(
                    title=_TITLE_MAP.get(run.agent_name, f"Working on {run.task_type}"),
                    status="needs_attention" if needs else ("working" if status_raw == "running" else status_raw),
                    progress=1 if status_raw == AgentRunStatus.RUNNING.value else 0,
                    total=1,
                    needs_attention=needs,
                    business_purpose=run.input_summary,
                    started_at=started,
                    duration_seconds=_duration_seconds(started),
                    advanced_details=ActiveWorkAdvanced(
                        agent_run_id=str(run.id),
                        agent_name=run.agent_name,
                    ),
                )
            )

        if len(items) < capped:
            tasks = self._session.scalars(
                select(ManagerTask)
                .where(ManagerTask.status.in_(list(_ACTIVE_TASK)))
                .order_by(ManagerTask.created_at.desc())
                .limit(capped - len(items))
            ).all()
            for task in tasks:
                status_raw = task.status.value if hasattr(task.status, "value") else str(task.status)
                needs = status_raw == ManagerTaskStatus.AWAITING_APPROVAL.value
                purpose = None
                if isinstance(task.payload, dict):
                    purpose = task.payload.get("goal") or task.payload.get("description")
                items.append(
                    ActiveWorkItem(
                        title=_TITLE_MAP.get(task.agent_name, f"Team task: {task.task_type}"),
                        status="needs_attention" if needs else status_raw,
                        progress=0,
                        total=1,
                        needs_attention=needs,
                        business_purpose=str(purpose) if purpose else task.task_type,
                        started_at=task.started_at or task.created_at,
                        duration_seconds=_duration_seconds(task.started_at or task.created_at),
                        advanced_details=ActiveWorkAdvanced(
                            manager_task_id=str(task.id),
                            manager_run_id=str(task.manager_run_id) if task.manager_run_id else None,
                            agent_name=task.agent_name,
                        ),
                    )
                )
        return ActiveWorkListView(items=items)


def _duration_seconds(started: datetime | None) -> int | None:
    if started is None:
        return None
    now = utc_now()
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0, int((now - started).total_seconds()))
