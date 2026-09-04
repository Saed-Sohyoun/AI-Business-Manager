"""Research Agent contract — find and verify potential business leads."""

from __future__ import annotations

from decimal import Decimal

from app.agents.contracts.schemas import AgentContract, AgentLimits, EscalationRule

RESEARCH_AGENT_ID = "research"

RESEARCH_AGENT_CONTRACT = AgentContract(
    agent_id=RESEARCH_AGENT_ID,
    version="1.0.0",
    name="Research Agent",
    description=(
        "Finds and verifies potential business leads from public sources. "
        "Stores evidence-backed company data. Never contacts businesses."
    ),
    responsibility="Find and verify potential business leads.",
    allowed_actions=frozenset(
        {
            "research.discover_companies",
            "discover_companies",
            "search_public_businesses",
            "verify_public_information",
            "normalize_data",
            "deduplicate",
            "store_evidence",
            "create_research_results",
        }
    ),
    forbidden_actions=frozenset(
        {
            "send_email",
            "sales.send_outreach",
            "send_sms",
            "send_message",
            "make_purchase",
            "commerce.purchase",
            "change_prices",
            "modify_financial_records",
            "finance.record_cost",
            "finance.transfer_money",
            "create_contracts",
            "contact_customers",
            "approve",
            "approvals.resolve",
            "change_own_permissions",
            "disable_safety",
            "execute_shell",
            "arbitrary_http",
        }
    ),
    allowed_tools=frozenset(
        {
            "search",
            "browser",
            "database",
        }
    ),
    forbidden_tools=frozenset(
        {
            "email",
            "sms",
            "payment",
            "shell",
            "arbitrary_http",
            "approval_resolve",
            "finance_ledger_write",
        }
    ),
    allowed_entities=frozenset(
        {
            "company",
            "company_source",
            "company_evidence",
            "lead_research_fields",
            "agent_run",
        }
    ),
    required_inputs=frozenset({"query"}),
    expected_outputs=frozenset({"ResearchResult"}),
    output_schema="ResearchResult",
    limits=AgentLimits(
        maximum_runtime_seconds=900,
        maximum_retries=3,
        maximum_tasks=1,
        maximum_cost=Decimal("2.00"),
        max_companies_per_run=20,
        # Audits are owned by Audit Agent — Research must not run audits.
        max_audits_per_run=None,
        max_search_requests=20,
        max_browser_runtime_seconds=120.0,
    ),
    approval_requirements=frozenset(),  # discover_companies is GREEN
    escalation_rules=(
        EscalationRule(
            trigger="external_communication",
            action="stop_request_manager",
            description=(
                "If the requested task requires external communication, "
                "STOP and request the Manager."
            ),
        ),
        EscalationRule(
            trigger="forbidden_action",
            action="stop_request_manager",
            description="Forbidden action requested — stop and escalate to Manager.",
        ),
    ),
    verification_rules=frozenset(
        {
            "evidence_required_for_stored_fields",
            "never_invent_contact_facts",
            "deduplicate_by_website_domain",
            "public_sources_only",
        }
    ),
    user_facing_scope_message=(
        "Research was stopped because the research team attempted an action "
        "outside its responsibilities."
    ),
)
