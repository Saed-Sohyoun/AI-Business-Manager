"""Delegation registry — Manager never performs specialized work itself."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.agents.manager.schemas import DelegationResult


class AgentExecutor(Protocol):
    def execute(
        self,
        *,
        agent_name: str,
        task_type: str,
        payload: dict,
        timeout_seconds: float,
    ) -> DelegationResult: ...


ExecutorFn = Callable[[dict, float], DelegationResult]


class RegistryExecutor:
    """Maps (agent_name, task_type) → callable. Unknown keys fail closed."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], ExecutorFn] = {}

    def register(self, agent_name: str, task_type: str, handler: ExecutorFn) -> None:
        self._handlers[(agent_name.lower(), task_type.lower())] = handler

    def has(self, agent_name: str, task_type: str) -> bool:
        return (agent_name.lower(), task_type.lower()) in self._handlers

    def execute(
        self,
        *,
        agent_name: str,
        task_type: str,
        payload: dict,
        timeout_seconds: float,
    ) -> DelegationResult:
        key = (agent_name.lower(), task_type.lower())
        handler = self._handlers.get(key)
        if handler is None:
            return DelegationResult(
                status="failed",
                summary=f"no_executor_registered:{agent_name}/{task_type}",
                retryable=False,
                error_message=f"no_executor_registered:{agent_name}/{task_type}",
            )
        try:
            return handler(payload, timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — boundary for delegated failures
            return DelegationResult(
                status="failed",
                summary=f"executor_exception:{type(exc).__name__}",
                retryable=True,
                error_message=f"{type(exc).__name__}: {exc}",
            )
