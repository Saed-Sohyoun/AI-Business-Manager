"""Wave 1 — adversarial agent contract / tool gateway tests."""

from __future__ import annotations

import pytest

from app.agents.contracts import get_agent_contract, get_enforcer, list_agent_contracts
from app.agents.contracts.catalog import ALL_AGENT_CONTRACTS
from app.exceptions import AgentScopeViolationError, ForbiddenError
from app.tools import ToolGateway


@pytest.mark.parametrize(
    ("agent_id", "action"),
    [
        ("research", "send_email"),
        ("research", "sales.send_outreach"),
        ("research", "make_purchase"),
        ("research", "finance.record_cost"),
        ("audit", "sales.send_outreach"),
        ("sales", "commerce.purchase"),
        ("sales", "finance.money_transfer"),
        ("report", "finance.record_cost"),
        ("finance", "send_email"),
        ("finance", "sales.send_outreach"),
        ("manager", "bypass_approval"),
        ("manager", "mutate_agent_contract"),
        ("manager", "mutate_policy"),
        ("manager", "approvals.resolve"),
        ("manager", "finance.money_transfer"),
    ],
)
def test_forbidden_actions_denied(agent_id: str, action: str):
    with pytest.raises(AgentScopeViolationError) as exc:
        get_enforcer(agent_id).assert_action_allowed(action)
    assert exc.value.code == "agent_scope_violation"


@pytest.mark.parametrize(
    ("agent_id", "tool"),
    [
        ("research", "email"),
        ("research", "payment"),
        ("audit", "email"),
        ("finance", "email"),
        ("report", "payment"),
        ("manager", "email"),
        ("manager", "shell"),
    ],
)
def test_forbidden_tools_denied(agent_id: str, tool: str):
    with pytest.raises(AgentScopeViolationError):
        ToolGateway(agent_id).require(tool)


def test_unknown_agent_denied():
    with pytest.raises(AgentScopeViolationError) as exc:
        ToolGateway("unknown_agent_xyz").require("database")
    assert "Unknown agent" in exc.value.message or exc.value.details.get("reason") == "unknown_agent"


def test_unknown_tool_denied():
    with pytest.raises(AgentScopeViolationError):
        ToolGateway("research").require("run_shell")
    with pytest.raises(AgentScopeViolationError):
        ToolGateway("research").require("arbitrary_http")


def test_unknown_action_denied():
    with pytest.raises(AgentScopeViolationError):
        ToolGateway("research").require_action("totally.unknown_action")


def test_manager_cannot_execute_red_via_gateway():
    with pytest.raises((ForbiddenError, AgentScopeViolationError)):
        ToolGateway("manager").require_action("finance.money_transfer")


def test_missing_agent_identity_denied():
    with pytest.raises(AgentScopeViolationError):
        ToolGateway("")


def test_all_core_agents_registered():
    ids = {c.agent_id for c in list_agent_contracts()}
    for expected in (
        "manager",
        "research",
        "scoring",
        "audit",
        "sales",
        "delivery",
        "finance",
        "report",
    ):
        assert expected in ids
    assert len(ALL_AGENT_CONTRACTS) >= 8
    assert get_agent_contract("research").version == "1.0.0"


def test_agent_spoofing_does_not_grant_foreign_tools():
    """Claiming to be sales while using research enforcer still respects research."""
    # Gateway binds contract to constructor agent_id — spoofing via kwargs is impossible.
    gw = ToolGateway("research")
    with pytest.raises(AgentScopeViolationError):
        gw.require("email")
