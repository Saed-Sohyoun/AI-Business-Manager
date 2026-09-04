"""Structured security event codes and persistence helper."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.security.redaction import redact_dict

logger = logging.getLogger(__name__)

# Stable event type codes (Wave 1)
AGENT_SCOPE_VIOLATION = "AGENT_SCOPE_VIOLATION"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
APPROVAL_PAYLOAD_MISMATCH = "APPROVAL_PAYLOAD_MISMATCH"
POLICY_DENIED = "POLICY_DENIED"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
RATE_LIMIT_REACHED = "RATE_LIMIT_REACHED"
WEBHOOK_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"
WEBHOOK_REPLAY_REJECTED = "WEBHOOK_REPLAY_REJECTED"
UNKNOWN_AGENT_DENIED = "UNKNOWN_AGENT_DENIED"
UNKNOWN_ACTION_DENIED = "UNKNOWN_ACTION_DENIED"
UNKNOWN_TOOL_DENIED = "UNKNOWN_TOOL_DENIED"
OWNER_PAUSED_ALL = "OWNER_PAUSED_ALL"
OWNER_RESUMED_AI = "OWNER_RESUMED_AI"
OWNER_PAUSED_AI = "OWNER_PAUSED_AI"
OWNER_PAUSED_OUTBOUND = "OWNER_PAUSED_OUTBOUND"
OWNER_RESUMED_OUTBOUND = "OWNER_RESUMED_OUTBOUND"
OWNER_PAUSED_SPENDING = "OWNER_PAUSED_SPENDING"
OWNER_RESUMED_SPENDING = "OWNER_RESUMED_SPENDING"
OWNER_PAUSED_BROWSER = "OWNER_PAUSED_BROWSER"
OWNER_RESUMED_BROWSER = "OWNER_RESUMED_BROWSER"
SAFE_MODE_ENTERED = "SAFE_MODE_ENTERED"
SAFE_MODE_CLEARED = "SAFE_MODE_CLEARED"
APPROVAL_APPROVED = "APPROVAL_APPROVED"
APPROVAL_REJECTED = "APPROVAL_REJECTED"
SYSTEM_CONTROL_DENIED = "SYSTEM_CONTROL_DENIED"


def record_security_event(
    session: Session | None,
    *,
    event_type: str,
    agent_id: str | None = None,
    action: str | None = None,
    tool: str | None = None,
    target: str | None = None,
    reason: str | None = None,
    execution_id: UUID | str | None = None,
    correlation_id: str | None = None,
    contract_version: str | None = None,
    details: dict[str, Any] | None = None,
) -> UUID | None:
    """Persist a security event when a session is available; always log structured."""
    safe_details = redact_dict(details or {})
    logger.warning(
        "security_event type=%s agent=%s action=%s tool=%s reason=%s execution_id=%s",
        event_type,
        agent_id,
        action,
        tool,
        reason,
        execution_id,
    )
    if session is None:
        return None
    from app.models.security_event import SecurityEvent

    row = SecurityEvent(
        event_type=event_type,
        agent_id=agent_id,
        action=action,
        tool=tool,
        target=target,
        reason=reason,
        execution_id=UUID(str(execution_id)) if execution_id else None,
        correlation_id=correlation_id,
        contract_version=contract_version,
        details=safe_details,
    )
    session.add(row)
    session.flush()
    return row.id
