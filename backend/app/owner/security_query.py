"""Owner security event listing — summarized, no secrets."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.security_event import SecurityEvent
from app.owner.schemas import SecurityEventAdvanced, SecurityEventListView, SecurityEventSummary
from app.security.events import (
    AGENT_SCOPE_VIOLATION,
    APPROVAL_PAYLOAD_MISMATCH,
    BUDGET_EXCEEDED,
    OWNER_PAUSED_ALL,
    SAFE_MODE_ENTERED,
    SYSTEM_CONTROL_DENIED,
    WEBHOOK_REPLAY_REJECTED,
    WEBHOOK_SIGNATURE_INVALID,
)

_SEVERITY = {
    OWNER_PAUSED_ALL: "critical",
    SAFE_MODE_ENTERED: "critical",
    AGENT_SCOPE_VIOLATION: "urgent",
    WEBHOOK_SIGNATURE_INVALID: "urgent",
    WEBHOOK_REPLAY_REJECTED: "urgent",
    APPROVAL_PAYLOAD_MISMATCH: "important",
    BUDGET_EXCEEDED: "urgent",
    SYSTEM_CONTROL_DENIED: "important",
}


class SecurityEventQueryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_events(self, *, limit: int = 50) -> SecurityEventListView:
        capped = max(1, min(limit, 200))
        rows = self._session.scalars(
            select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(capped)
        ).all()
        items: list[SecurityEventSummary] = []
        for row in rows:
            severity = _SEVERITY.get(row.event_type, "important")
            title = row.event_type.replace("_", " ").title()
            summary = row.reason or title
            items.append(
                SecurityEventSummary(
                    id=row.id,
                    title=title,
                    summary=summary[:500],
                    severity=severity,  # type: ignore[arg-type]
                    created_at=row.created_at,
                    advanced_details=SecurityEventAdvanced(
                        event_type=row.event_type,
                        agent=row.agent_id,
                        execution_id=str(row.execution_id) if row.execution_id else None,
                        timestamp=row.created_at,
                        reason=row.reason,
                        policy_version=row.contract_version,
                        action=row.action,
                        tool=row.tool,
                    ),
                )
            )
        return SecurityEventListView(items=items)
