"""Owner execution states — explicit FSM for governed owner commands."""

from __future__ import annotations

import enum


class OwnerExecutionState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


# Legal transitions — unknown = deny
OWNER_EXECUTION_TRANSITIONS: dict[OwnerExecutionState, frozenset[OwnerExecutionState]] = {
    OwnerExecutionState.QUEUED: frozenset(
        {
            OwnerExecutionState.RUNNING,
            OwnerExecutionState.CANCELLED,
            OwnerExecutionState.BLOCKED,
            OwnerExecutionState.FAILED,
        }
    ),
    OwnerExecutionState.RUNNING: frozenset(
        {
            OwnerExecutionState.WAITING,
            OwnerExecutionState.WAITING_FOR_APPROVAL,
            OwnerExecutionState.COMPLETED,
            OwnerExecutionState.PARTIALLY_COMPLETED,
            OwnerExecutionState.FAILED,
            OwnerExecutionState.CANCELLED,
            OwnerExecutionState.BLOCKED,
        }
    ),
    OwnerExecutionState.WAITING: frozenset(
        {
            OwnerExecutionState.RUNNING,
            OwnerExecutionState.FAILED,
            OwnerExecutionState.CANCELLED,
            OwnerExecutionState.BLOCKED,
        }
    ),
    OwnerExecutionState.WAITING_FOR_APPROVAL: frozenset(
        {
            OwnerExecutionState.RUNNING,
            OwnerExecutionState.COMPLETED,
            OwnerExecutionState.PARTIALLY_COMPLETED,
            OwnerExecutionState.FAILED,
            OwnerExecutionState.CANCELLED,
        }
    ),
    OwnerExecutionState.BLOCKED: frozenset(
        {
            OwnerExecutionState.RUNNING,
            OwnerExecutionState.CANCELLED,
            OwnerExecutionState.FAILED,
        }
    ),
    OwnerExecutionState.COMPLETED: frozenset(),
    OwnerExecutionState.PARTIALLY_COMPLETED: frozenset(),
    OwnerExecutionState.FAILED: frozenset(),
    OwnerExecutionState.CANCELLED: frozenset(),
}


def can_transition(current: OwnerExecutionState | str, nxt: OwnerExecutionState | str) -> bool:
    cur = current if isinstance(current, OwnerExecutionState) else OwnerExecutionState(current)
    nxt_s = nxt if isinstance(nxt, OwnerExecutionState) else OwnerExecutionState(nxt)
    if cur == nxt_s:
        return True  # idempotent same-state
    return nxt_s in OWNER_EXECUTION_TRANSITIONS.get(cur, frozenset())


class OwnerCommandType(str, enum.Enum):
    FIND_OPPORTUNITIES = "find_opportunities"
    GENERATE_REPORT = "generate_report"
