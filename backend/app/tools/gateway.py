"""Controlled tool gateway — agents request typed tools; contracts + policy enforced.

Does not expose run_shell / execute_code / arbitrary_http / arbitrary_sql.
Wraps existing services incrementally; providers stay behind typed services.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.contracts.enforcement import AgentContractEnforcer, get_enforcer
from app.agents.contracts.registry import get_agent_contract
from app.approvals.policy import ApprovalPolicy, normalize_action_type
from app.exceptions import AgentScopeViolationError, ForbiddenError
from app.models.enums import RiskLevel
from app.security.events import (
    AGENT_SCOPE_VIOLATION,
    POLICY_DENIED,
    UNKNOWN_ACTION_DENIED,
    UNKNOWN_AGENT_DENIED,
    UNKNOWN_TOOL_DENIED,
    record_security_event,
)
from app.security.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

# Explicitly never exposed through the gateway
FORBIDDEN_GATEWAY_TOOLS = frozenset(
    {
        "run_shell",
        "execute_code",
        "arbitrary_http",
        "arbitrary_sql",
        "generic_tool_call",
        "shell",
        "code_exec",
        # Owner control plane — agents must never invoke these
        "owner_pause_all",
        "owner_resume_outbound",
        "owner_resume_spending",
        "owner_resume_ai",
        "owner_clear_safe_mode",
        "owner_set_system_control",
        "system_control",
        "safe_mode_clear",
        "pause_all",
        "resume_outbound",
        "resume_spending",
        "clear_safe_mode",
    }
)

OWNER_CONTROL_ACTIONS = frozenset(
    {
        "owner.pause_all",
        "owner.resume_outbound",
        "owner.resume_spending",
        "owner.resume_ai",
        "owner.clear_safe_mode",
        "owner.set_control",
        "system.pause_all",
        "system.clear_safe_mode",
        "system.resume_outbound",
        "system.resume_spending",
    }
)


class ToolGateway:
    """Gate between agent identity and external/internal tools."""

    def __init__(
        self,
        agent_id: str,
        *,
        context: ExecutionContext | None = None,
        task: str | None = None,
        execution_id: UUID | str | None = None,
        correlation_id: str | None = None,
        session: Session | None = None,
        enforcer: AgentContractEnforcer | None = None,
        policy: ApprovalPolicy | None = None,
    ) -> None:
        if not agent_id or not str(agent_id).strip():
            raise AgentScopeViolationError(
                "Governed operations require an agent identity.",
                details={"reason": "missing_agent_id"},
            )
        self.agent_id = agent_id.strip().lower()
        try:
            contract = get_agent_contract(self.agent_id)
        except AgentScopeViolationError:
            record_security_event(
                session,
                event_type=UNKNOWN_AGENT_DENIED,
                agent_id=self.agent_id,
                reason="unknown_agent",
            )
            raise
        self.contract = contract
        if context is not None:
            self.context = context
        else:
            ctx: dict[str, Any] = {
                "agent_id": self.agent_id,
                "task_id": task,
                "correlation_id": correlation_id,
                "contract_version": contract.version,
            }
            if execution_id is not None:
                ctx["execution_id"] = UUID(str(execution_id))
            self.context = ExecutionContext(**ctx)
        self.task = task or self.context.task_id
        self.execution_id = execution_id or self.context.execution_id
        self.correlation_id = correlation_id or self.context.correlation_id
        self._session = session
        self._enforcer = enforcer or AgentContractEnforcer(contract)
        self._policy = policy or ApprovalPolicy()

    def require_action(self, action: str, *, target: str | None = None, **extra: Any) -> None:
        action_norm = normalize_action_type(action) if action else ""
        if not action_norm:
            record_security_event(
                self._session,
                event_type=UNKNOWN_ACTION_DENIED,
                agent_id=self.agent_id,
                action=action,
                reason="empty_action",
                execution_id=self.execution_id,
                correlation_id=self.correlation_id,
                contract_version=self.contract.version,
            )
            raise AgentScopeViolationError(
                "Unknown action — access denied.",
                details={"agent": self.agent_id, "reason": "empty_action"},
            )
        if action_norm in OWNER_CONTROL_ACTIONS or action_norm.startswith("owner."):
            record_security_event(
                self._session,
                event_type=AGENT_SCOPE_VIOLATION,
                agent_id=self.agent_id,
                action=action_norm,
                reason="agent_cannot_use_owner_controls",
                execution_id=self.execution_id,
                correlation_id=self.correlation_id,
                contract_version=self.contract.version,
            )
            raise ForbiddenError(
                "Agents cannot control owner system settings.",
                details={"agent": self.agent_id, "action": action_norm},
            )
        if not self.contract.allows_action(action_norm):
            record_security_event(
                self._session,
                event_type=AGENT_SCOPE_VIOLATION,
                agent_id=self.agent_id,
                action=action_norm,
                target=target,
                reason="action_not_allowed",
                execution_id=self.execution_id,
                correlation_id=self.correlation_id,
                contract_version=self.contract.version,
            )
            self._enforcer.assert_action_allowed(
                action_norm,
                task=self.task,
                execution_id=self.execution_id,
                extra={"target": target, **(extra or {})},
            )
            return  # unreachable — assert raises
        # Policy awareness: RED actions are never agent-executable via gateway
        entry = self._policy.get_entry(action_norm)
        if entry.risk_level == RiskLevel.RED or not entry.agent_executable:
            record_security_event(
                self._session,
                event_type=POLICY_DENIED,
                agent_id=self.agent_id,
                action=action_norm,
                reason="red_or_non_executable",
                execution_id=self.execution_id,
                correlation_id=self.correlation_id,
                contract_version=self.contract.version,
            )
            raise ForbiddenError(
                "Action blocked by policy — agents cannot execute this action.",
                details={
                    "agent": self.agent_id,
                    "action": action_norm,
                    "risk_level": entry.risk_level.value,
                },
            )
        self._enforcer.assert_action_allowed(
            action_norm,
            task=self.task,
            execution_id=self.execution_id,
            extra={"target": target, **(extra or {})},
        )

    def require(self, tool: str, *, target: str | None = None, **extra: Any) -> None:
        tool_norm = (tool or "").strip().lower()
        if not tool_norm:
            raise AgentScopeViolationError(
                "Unknown tool — access denied.",
                details={"agent": self.agent_id, "reason": "empty_tool"},
            )
        if tool_norm in FORBIDDEN_GATEWAY_TOOLS:
            self._deny_tool(tool_norm, target=target, reason="absolutely_forbidden_tool")
        # System control enforcement for browser tools
        if tool_norm in {"browser", "browser_fetch", "browser_automation", "fetch_page"}:
            if self._session is not None:
                from app.owner.controls import SystemControlService

                SystemControlService(self._session).assert_browser(actor=self.agent_id)
        if not self.contract.allows_tool(tool_norm):
            self._deny_tool(tool_norm, target=target, reason="tool_not_allowed_for_agent")
        self._enforcer.assert_tool_allowed(
            tool_norm,
            task=self.task,
            execution_id=self.execution_id,
            extra={"target": target, **(extra or {})},
        )

    def _deny_tool(self, tool: str, *, target: str | None, reason: str) -> None:
        event = UNKNOWN_TOOL_DENIED if reason.startswith("unknown") else AGENT_SCOPE_VIOLATION
        record_security_event(
            self._session,
            event_type=event,
            agent_id=self.agent_id,
            tool=tool,
            target=target,
            reason=reason,
            execution_id=self.execution_id,
            correlation_id=self.correlation_id,
            contract_version=self.contract.version,
        )
        raise AgentScopeViolationError(
            self.contract.user_facing_scope_message,
            details={
                "agent": self.agent_id,
                "requested_action": f"tool:{tool}",
                "reason": reason,
                "task": self.task,
                "execution_id": str(self.execution_id) if self.execution_id else None,
                "contract_version": self.contract.version,
            },
        )
