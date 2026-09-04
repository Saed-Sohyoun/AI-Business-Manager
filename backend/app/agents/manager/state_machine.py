"""Task state machine — explicit allowed transitions only."""

from __future__ import annotations

from app.models.enums import ManagerTaskStatus

# Terminal statuses cannot transition further.
TERMINAL_STATUSES: frozenset[ManagerTaskStatus] = frozenset(
    {
        ManagerTaskStatus.SUCCEEDED,
        ManagerTaskStatus.CANCELLED,
        ManagerTaskStatus.SKIPPED,
        ManagerTaskStatus.INVALID,
    }
)

ALLOWED_TRANSITIONS: dict[ManagerTaskStatus, frozenset[ManagerTaskStatus]] = {
    ManagerTaskStatus.PENDING: frozenset(
        {
            ManagerTaskStatus.READY,
            ManagerTaskStatus.INVALID,
            ManagerTaskStatus.CANCELLED,
            ManagerTaskStatus.SKIPPED,
        }
    ),
    ManagerTaskStatus.READY: frozenset(
        {
            ManagerTaskStatus.RUNNING,
            ManagerTaskStatus.AWAITING_APPROVAL,
            ManagerTaskStatus.CANCELLED,
            ManagerTaskStatus.SKIPPED,
            ManagerTaskStatus.INVALID,
        }
    ),
    ManagerTaskStatus.AWAITING_APPROVAL: frozenset(
        {
            ManagerTaskStatus.READY,
            ManagerTaskStatus.CANCELLED,
            ManagerTaskStatus.SKIPPED,
        }
    ),
    ManagerTaskStatus.RUNNING: frozenset(
        {
            ManagerTaskStatus.SUCCEEDED,
            ManagerTaskStatus.FAILED,
            ManagerTaskStatus.TIMED_OUT,
            ManagerTaskStatus.AWAITING_APPROVAL,
        }
    ),
    ManagerTaskStatus.FAILED: frozenset(
        {
            ManagerTaskStatus.RETRYING,
            ManagerTaskStatus.CANCELLED,
        }
    ),
    ManagerTaskStatus.TIMED_OUT: frozenset(
        {
            ManagerTaskStatus.RETRYING,
            ManagerTaskStatus.CANCELLED,
        }
    ),
    ManagerTaskStatus.RETRYING: frozenset(
        {
            ManagerTaskStatus.READY,
            ManagerTaskStatus.CANCELLED,
        }
    ),
    ManagerTaskStatus.SUCCEEDED: frozenset(),
    ManagerTaskStatus.CANCELLED: frozenset(),
    ManagerTaskStatus.SKIPPED: frozenset(),
    ManagerTaskStatus.INVALID: frozenset(),
}


class InvalidTaskTransition(ValueError):
    """Raised when a disallowed task state transition is attempted."""


def can_transition(current: ManagerTaskStatus, target: ManagerTaskStatus) -> bool:
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def transition(current: ManagerTaskStatus, target: ManagerTaskStatus) -> ManagerTaskStatus:
    if current == target:
        return current
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTaskTransition(
            f"cannot transition task from {current.value} to {target.value}"
        )
    return target


def is_terminal(status: ManagerTaskStatus) -> bool:
    return status in TERMINAL_STATUSES


def is_executable(status: ManagerTaskStatus) -> bool:
    return status == ManagerTaskStatus.READY
