"""Agent contract registry — source of truth for registered agent boundaries.

UNKNOWN AGENT / ACTION / TOOL = DENY (fail closed).
"""

from __future__ import annotations

from app.agents.contracts.catalog import ALL_AGENT_CONTRACTS
from app.agents.contracts.schemas import AgentContract
from app.exceptions import AgentScopeViolationError, NotFoundError

_REGISTRY: dict[str, AgentContract] = {c.agent_id: c for c in ALL_AGENT_CONTRACTS}


def register_agent_contract(contract: AgentContract, *, replace: bool = False) -> None:
    """Register or replace a contract (tests / future agent onboarding)."""
    if contract.agent_id in _REGISTRY and not replace:
        raise ValueError(f"contract already registered: {contract.agent_id}")
    _REGISTRY[contract.agent_id] = contract


def get_agent_contract(agent_id: str) -> AgentContract:
    """Return contract or raise AgentScopeViolationError for unknown agents (fail closed)."""
    key = (agent_id or "").strip().lower()
    contract = _REGISTRY.get(key)
    if contract is None:
        raise AgentScopeViolationError(
            "Unknown agent — access denied.",
            details={
                "agent": agent_id,
                "reason": "unknown_agent",
                "policy": "agent_contract.registry",
            },
        )
    return contract


def try_get_agent_contract(agent_id: str) -> AgentContract | None:
    """Lookup without raising (tests / introspection)."""
    return _REGISTRY.get((agent_id or "").strip().lower())


def require_known_agent(agent_id: str) -> AgentContract:
    """Alias — fail closed."""
    return get_agent_contract(agent_id)


def list_agent_contracts() -> list[AgentContract]:
    return list(_REGISTRY.values())


def reset_registry_for_tests(contracts: list[AgentContract] | None = None) -> None:
    """Test helper — restore default catalog or inject fixtures."""
    _REGISTRY.clear()
    for c in contracts if contracts is not None else ALL_AGENT_CONTRACTS:
        _REGISTRY[c.agent_id] = c
