"""Structured observability events."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.security.redaction import redact_dict

logger = logging.getLogger("app.observability")


def emit_event(
    event_type: str,
    *,
    level: str = "INFO",
    request_id: str | None = None,
    correlation_id: str | None = None,
    execution_id: str | None = None,
    goal_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    action_id: str | None = None,
    provider: str | None = None,
    duration_ms: float | None = None,
    status: str | None = None,
    cost: Any = None,
    error_code: str | None = None,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "level": level.upper(),
    }
    optional = {
        "request_id": request_id,
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "action_id": action_id,
        "provider": provider,
        "duration_ms": duration_ms,
        "status": status,
        "cost": str(cost) if cost is not None else None,
        "error_code": error_code,
    }
    for key, value in optional.items():
        if value is not None:
            payload[key] = value
    if extra:
        payload.update(redact_dict(extra))
    line = json.dumps(payload, default=str)
    log_fn = logger.info if level.upper() != "ERROR" else logger.error
    log_fn(line)
