"""Enforce agent contracts independently of the LLM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.contracts.registry import get_agent_contract
from app.agents.contracts.schemas import AgentContract
from app.exceptions import AgentScopeViolationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EscalationResult:
    """Safe stop + handoff signal when work exceeds agent scope."""

    escalate: bool
    target: str
    reason: str
    trigger: str
    agent_id: str
    user_message: str
    details: dict[str, Any]


class AgentContractEnforcer:
    """Validate actions/tools against a registered agent contract."""

    def __init__(self, contract: AgentContract) -> None:
        self.contract = contract

    @property
    def agent_id(self) -> str:
        return self.contract.agent_id

    def assert_action_allowed(
        self,
        action: str,
        *,
        task: str | None = None,
        execution_id: UUID | str | None = None,
        policy: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.contract.allows_action(action):
            return
        details = {
            "agent": self.contract.agent_id,
            "requested_action": action,
            "reason": "action_not_in_allowed_set_or_explicitly_forbidden",
            "task": task,
            "policy": policy or "agent_contract",
            "execution_id": str(execution_id) if execution_id else None,
            "allowed_actions": sorted(self.contract.allowed_actions),
            **(extra or {}),
        }
        logger.warning(
            "AGENT_SCOPE_VIOLATION agent=%s action=%s task=%s execution_id=%s",
            self.contract.agent_id,
            action,
            task,
            execution_id,
        )
        raise AgentScopeViolationError(
            self.contract.user_facing_scope_message,
            details={k: v for k, v in details.items() if v is not None},
        )

    def assert_tool_allowed(
        self,
        tool: str,
        *,
        task: str | None = None,
        execution_id: UUID | str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.contract.allows_tool(tool):
            return
        details = {
            "agent": self.contract.agent_id,
            "requested_action": f"tool:{tool}",
            "reason": "tool_not_allowed_for_agent",
            "task": task,
            "policy": "agent_contract.tools",
            "execution_id": str(execution_id) if execution_id else None,
            "allowed_tools": sorted(self.contract.allowed_tools),
            **(extra or {}),
        }
        logger.warning(
            "AGENT_SCOPE_VIOLATION agent=%s tool=%s task=%s execution_id=%s",
            self.contract.agent_id,
            tool,
            task,
            execution_id,
        )
        raise AgentScopeViolationError(
            self.contract.user_facing_scope_message,
            details={k: v for k, v in details.items() if v is not None},
        )

    def escalate_external_communication(
        self,
        *,
        reason: str,
        task: str | None = None,
        execution_id: UUID | str | None = None,
    ) -> EscalationResult:
        """STOP and request Manager — Research must not contact externally."""
        logger.info(
            "agent_escalation agent=%s trigger=external_communication reason=%s",
            self.contract.agent_id,
            reason,
        )
        return EscalationResult(
            escalate=True,
            target="manager",
            reason=reason,
            trigger="external_communication",
            agent_id=self.contract.agent_id,
            user_message=(
                "Research stopped: this task needs external communication. "
                "The manager must decide next steps."
            ),
            details={
                "task": task,
                "execution_id": str(execution_id) if execution_id else None,
            },
        )


def get_enforcer(agent_id: str) -> AgentContractEnforcer:
    return AgentContractEnforcer(get_agent_contract(agent_id))


def enforce_action(agent_id: str, action: str, **kwargs: Any) -> None:
    get_enforcer(agent_id).assert_action_allowed(action, **kwargs)


def enforce_tool(agent_id: str, tool: str, **kwargs: Any) -> None:
    get_enforcer(agent_id).assert_tool_allowed(tool, **kwargs)
