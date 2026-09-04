"""Execution limits and stop-condition evaluation for Manager runs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.config import Settings


@dataclass(frozen=True, slots=True)
class LimitSnapshot:
    elapsed_seconds: float
    estimated_cost: Decimal
    tasks_created: int
    retries_used: int
    max_runtime_seconds: int
    max_cost: Decimal
    max_tasks: int
    max_retries: int
    daily_spend: Decimal = Decimal("0")
    daily_budget_limit: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class StopDecision:
    should_stop: bool
    reason: str | None = None


def evaluate_stop(snapshot: LimitSnapshot) -> StopDecision:
    """Safe stopping conditions — never allow unbounded Manager execution."""
    if snapshot.elapsed_seconds >= snapshot.max_runtime_seconds:
        return StopDecision(True, "runtime_limit")
    if snapshot.estimated_cost >= snapshot.max_cost:
        return StopDecision(True, "cost_limit")
    if snapshot.tasks_created > snapshot.max_tasks:
        return StopDecision(True, "task_limit")
    # Global retry budget across the run (in addition to per-task max_retries)
    global_retry_budget = snapshot.max_retries * max(snapshot.tasks_created, 1)
    if snapshot.retries_used >= global_retry_budget and snapshot.retries_used > 0:
        return StopDecision(True, "retry_limit")
    if (
        snapshot.daily_budget_limit > 0
        and (snapshot.daily_spend + snapshot.estimated_cost) > snapshot.daily_budget_limit
    ):
        return StopDecision(True, "daily_budget_limit")
    return StopDecision(False, None)


def limits_from_settings(settings: Settings) -> dict[str, int | Decimal]:
    return {
        "max_runtime_seconds": settings.max_agent_runtime_seconds,
        "max_cost": settings.max_ai_cost_per_run,
        "max_tasks": settings.max_tasks_per_run,
        "max_retries": settings.max_retries,
    }


def can_retry(*, attempt_count: int, max_retries: int, retryable: bool) -> bool:
    if not retryable:
        return False
    # attempt_count includes the failed attempt; retries used = attempt_count - 1
    return (attempt_count - 1) < max_retries
