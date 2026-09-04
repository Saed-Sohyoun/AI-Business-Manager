"""Machine-readable agent contracts — boundaries independent of the LLM."""

from __future__ import annotations

from app.agents.contracts.enforcement import (
    AgentContractEnforcer,
    EscalationResult,
    enforce_action,
    enforce_tool,
    get_enforcer,
)
from app.agents.contracts.registry import (
    get_agent_contract,
    list_agent_contracts,
    register_agent_contract,
    try_get_agent_contract,
)
from app.agents.contracts.schemas import AgentContract, AgentLimits, EscalationRule

__all__ = [
    "AgentContract",
    "AgentContractEnforcer",
    "AgentLimits",
    "EscalationResult",
    "EscalationRule",
    "enforce_action",
    "enforce_tool",
    "get_agent_contract",
    "get_enforcer",
    "list_agent_contracts",
    "register_agent_contract",
    "try_get_agent_contract",
]
