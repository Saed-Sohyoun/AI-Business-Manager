"""Tests for Research AgentContract — boundaries independent of the LLM."""

from __future__ import annotations

import pytest

from app.agents.contracts import (
    get_agent_contract,
    get_enforcer,
    list_agent_contracts,
)
from app.agents.contracts.research import RESEARCH_AGENT_CONTRACT, RESEARCH_AGENT_ID
from app.agents.research import ResearchAgent, ResearchResult, ResearchRunResult
from app.exceptions import AgentScopeViolationError
from app.tools import ToolGateway


def test_research_contract_registered():
    contract = get_agent_contract(RESEARCH_AGENT_ID)
    assert contract.agent_id == "research"
    assert contract.name == "Research Agent"
    assert contract.output_schema == "ResearchResult"
    assert contract.limits.max_companies_per_run == 20
    assert "search" in contract.allowed_tools
    assert "browser" in contract.allowed_tools
    assert "database" in contract.allowed_tools
    assert contract in list_agent_contracts() or any(
        c.agent_id == "research" for c in list_agent_contracts()
    )


def test_research_result_alias():
    assert ResearchResult is ResearchRunResult


def test_research_allows_discover_companies():
    enforcer = get_enforcer(RESEARCH_AGENT_ID)
    enforcer.assert_action_allowed("research.discover_companies")
    enforcer.assert_action_allowed("discover_companies")
    enforcer.assert_action_allowed("store_evidence")
    enforcer.assert_tool_allowed("search")
    enforcer.assert_tool_allowed("browser")
    enforcer.assert_tool_allowed("database")


@pytest.mark.parametrize(
    "action",
    [
        "send_email",
        "sales.send_outreach",
        "send_sms",
        "make_purchase",
        "commerce.purchase",
        "change_prices",
        "modify_financial_records",
        "create_contracts",
        "contact_customers",
        "approvals.resolve",
        "change_own_permissions",
        "execute_shell",
    ],
)
def test_research_forbids_external_and_privilege_actions(action: str):
    enforcer = get_enforcer(RESEARCH_AGENT_ID)
    with pytest.raises(AgentScopeViolationError) as exc_info:
        enforcer.assert_action_allowed(action, task="discover_companies", execution_id="run-1")
    err = exc_info.value
    assert err.code == "agent_scope_violation"
    assert "outside its responsibilities" in err.message
    assert err.details["agent"] == "research"
    assert err.details["requested_action"] == action


@pytest.mark.parametrize("tool", ["email", "sms", "payment", "shell", "arbitrary_http"])
def test_research_forbids_tools(tool: str):
    gateway = ToolGateway(RESEARCH_AGENT_ID, task="discover_companies")
    with pytest.raises(AgentScopeViolationError) as exc_info:
        gateway.require(tool)
    assert exc_info.value.code == "agent_scope_violation"
    assert exc_info.value.details["requested_action"] == f"tool:{tool}"


def test_research_escalates_external_communication():
    enforcer = get_enforcer(RESEARCH_AGENT_ID)
    result = enforcer.escalate_external_communication(
        reason="task_requires_sending_email",
        task="discover_companies",
    )
    assert result.escalate is True
    assert result.target == "manager"
    assert result.trigger == "external_communication"


def test_research_agent_request_action_blocks_send_email(db_session, settings):
    from unittest.mock import MagicMock

    from app.config import Settings

    agent = ResearchAgent(
        session=db_session,
        search_service=MagicMock(),
        browser_service=None,
        settings=Settings(app_env="test", database_url="sqlite+pysqlite:///:memory:"),
        sleep_fn=lambda _s: None,
    )
    with pytest.raises(AgentScopeViolationError):
        agent.request_action("send_email")


def test_research_agent_escalate_helper(db_session):
    from unittest.mock import MagicMock

    from app.config import Settings

    agent = ResearchAgent(
        session=db_session,
        search_service=MagicMock(),
        browser_service=None,
        settings=Settings(app_env="test", database_url="sqlite+pysqlite:///:memory:"),
        sleep_fn=lambda _s: None,
    )
    result = agent.escalate_if_external_communication("owner_asked_to_email_leads")
    assert result.status == "escalated"
    assert result.escalation is not None
    assert result.escalation["target"] == "manager"


def test_research_contract_does_not_allow_audits():
    """Audits belong to Audit Agent — Research must not claim audit tools/actions."""
    contract = RESEARCH_AGENT_CONTRACT
    assert contract.limits.max_audits_per_run is None
    assert not contract.allows_action("audit.audit_digital_presence")
    assert not contract.allows_tool("audit")
