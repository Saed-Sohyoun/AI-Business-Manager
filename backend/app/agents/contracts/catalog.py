"""Registered AgentContracts — fail closed for unknown agents/actions/tools."""

from __future__ import annotations

from decimal import Decimal

from app.agents.contracts.research import RESEARCH_AGENT_CONTRACT
from app.agents.contracts.schemas import AgentContract, AgentLimits, EscalationRule

_COMMON_FORBIDDEN_ACTIONS = frozenset(
    {
        "execute_shell",
        "arbitrary_http",
        "arbitrary_sql",
        "change_own_permissions",
        "disable_safety",
        "mutate_agent_contract",
        "mutate_policy",
        "approvals.resolve",
    }
)
_COMMON_FORBIDDEN_TOOLS = frozenset(
    {
        "shell",
        "arbitrary_http",
        "arbitrary_sql",
        "code_exec",
        "approval_resolve",
    }
)

SCORING_AGENT_CONTRACT = AgentContract(
    agent_id="scoring",
    version="1.0.0",
    name="Lead Scoring",
    description="Deterministic lead scoring from verified facts.",
    responsibility="Calculate and explain lead scores.",
    allowed_actions=frozenset(
        {"scoring.score_companies", "score_companies", "explain_score", "store_scoring_evidence"}
    ),
    forbidden_actions=_COMMON_FORBIDDEN_ACTIONS
    | frozenset(
        {
            "send_email",
            "sales.send_outreach",
            "contact_customers",
            "make_purchase",
            "modify_financial_records",
            "finance.record_cost",
        }
    ),
    allowed_tools=frozenset({"database"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS | frozenset({"email", "browser", "search", "payment"}),
    allowed_entities=frozenset({"company", "company_score", "company_evidence"}),
    resource_scope=frozenset({"company_scores", "company_evidence"}),
    required_inputs=frozenset({"company_id"}),
    expected_outputs=frozenset({"LeadScoreResult"}),
    output_schema="LeadScoreResult",
    limits=AgentLimits(maximum_runtime_seconds=120, maximum_retries=1, maximum_tasks=50),
    user_facing_scope_message=(
        "Scoring was stopped because the scoring team attempted an action "
        "outside its responsibilities."
    ),
)

AUDIT_AGENT_CONTRACT = AgentContract(
    agent_id="audit",
    version="1.0.0",
    name="Audit Agent",
    description="Public digital-presence audits; no outreach.",
    responsibility="Analyze public websites and identify opportunities.",
    allowed_actions=frozenset(
        {
            "audit.audit_digital_presence",
            "audit_digital_presence",
            "analyze_website",
            "store_audit",
        }
    ),
    forbidden_actions=_COMMON_FORBIDDEN_ACTIONS
    | frozenset(
        {
            "send_email",
            "sales.send_outreach",
            "contact_customers",
            "make_purchase",
            "change_websites",
            "finance.record_cost",
        }
    ),
    allowed_tools=frozenset({"browser", "search", "database", "ai"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS | frozenset({"email", "payment", "sms"}),
    allowed_entities=frozenset({"company", "company_audit", "company_evidence"}),
    resource_scope=frozenset({"company_audits"}),
    required_inputs=frozenset({"company_ids"}),
    expected_outputs=frozenset({"AuditRunResult"}),
    output_schema="AuditRunResult",
    limits=AgentLimits(
        maximum_runtime_seconds=900,
        maximum_retries=2,
        max_audits_per_run=10,
        maximum_cost=Decimal("2.00"),
    ),
    user_facing_scope_message=(
        "The audit was stopped because the audit team attempted an action "
        "outside its responsibilities."
    ),
)

SALES_AGENT_CONTRACT = AgentContract(
    agent_id="sales",
    version="1.0.0",
    name="Sales Agent",
    description="Draft personalized outreach; send only via approval.",
    responsibility="Create outreach drafts and recommend follow-ups.",
    allowed_actions=frozenset(
        {
            "sales.draft_outreach",
            "draft_outreach",
            "sales.send_outreach",
            "sales.first_outreach",
            "sales.send_followup",
            "request_send_approval",
            "classify_responses",
        }
    ),
    forbidden_actions=_COMMON_FORBIDDEN_ACTIONS
    | frozenset(
        {
            "make_purchase",
            "commerce.purchase",
            "finance.money_transfer",
            "create_contracts",
            "change_prices",
            "invent_personalization",
        }
    ),
    allowed_tools=frozenset({"database", "ai", "email"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS | frozenset({"payment", "shell"}),
    allowed_entities=frozenset({"lead", "outreach", "outbound_message", "company", "approval"}),
    resource_scope=frozenset({"outreaches", "leads"}),
    required_inputs=frozenset({"company_id", "lead_id"}),
    expected_outputs=frozenset({"SalesRunResult"}),
    output_schema="SalesRunResult",
    limits=AgentLimits(maximum_runtime_seconds=300, maximum_retries=2, maximum_cost=Decimal("1.00")),
    approval_requirements=frozenset(
        {"sales.send_outreach", "sales.first_outreach", "sales.send_followup"}
    ),
    user_facing_scope_message=(
        "Sales work was stopped because the sales team attempted an action "
        "outside its responsibilities."
    ),
)

DELIVERY_AGENT_CONTRACT = AgentContract(
    agent_id="delivery",
    version="1.0.0",
    name="Delivery Agent",
    description="Manage customer projects and deliverables.",
    responsibility="Organize delivery work and verify completion.",
    allowed_actions=frozenset(
        {
            "delivery.create_project",
            "delivery.create_tasks",
            "delivery.execute_safe_task",
            "delivery.execute_sensitive_task",
            "delivery.verify_task",
            "delivery.produce_deliverable",
            "delivery.verify_project",
            "delivery.complete_project",
        }
    ),
    forbidden_actions=_COMMON_FORBIDDEN_ACTIONS
    | frozenset(
        {
            "send_email",
            "sales.send_outreach",
            "finance.money_transfer",
            "legal.contract",
            "change_commercial_terms",
        }
    ),
    allowed_tools=frozenset({"database"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS | frozenset({"email", "payment", "browser"}),
    allowed_entities=frozenset(
        {"customer", "delivery_project", "project_task", "deliverable", "approval"}
    ),
    resource_scope=frozenset({"delivery"}),
    expected_outputs=frozenset({"DeliveryRunResult"}),
    output_schema="DeliveryRunResult",
    limits=AgentLimits(maximum_runtime_seconds=600, maximum_retries=2),
    approval_requirements=frozenset({"delivery.execute_sensitive_task"}),
)

FINANCE_AGENT_CONTRACT = AgentContract(
    agent_id="finance",
    version="1.0.0",
    name="Finance Agent",
    description="Ledger calculations and reports — no money movement.",
    responsibility="Calculate financial metrics and record authorized ledger entries.",
    allowed_actions=frozenset(
        {
            "finance.record_cost",
            "finance.record_revenue",
            "finance.calculate_metrics",
            "finance.report",
            "record_cost",
            "record_revenue",
            "calculate_metrics",
        }
    ),
    forbidden_actions=_COMMON_FORBIDDEN_ACTIONS
    | frozenset(
        {
            "send_email",
            "sales.send_outreach",
            "finance.money_transfer",
            "finance.autonomous_payment",
            "make_purchase",
        }
    ),
    allowed_tools=frozenset({"database"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS | frozenset({"email", "payment", "browser", "search"}),
    allowed_entities=frozenset({"cost_entry", "revenue_entry", "financial_metric"}),
    resource_scope=frozenset({"finance"}),
    expected_outputs=frozenset({"FinanceRunResult"}),
    output_schema="FinanceRunResult",
    limits=AgentLimits(maximum_runtime_seconds=180, maximum_retries=1, maximum_cost=Decimal("0")),
)

REPORT_AGENT_CONTRACT = AgentContract(
    agent_id="report",
    version="1.0.0",
    name="Report Agent",
    description="Read metrics and generate business reports.",
    responsibility="Generate factual reports and recommendations.",
    allowed_actions=frozenset({"report.generate", "generate", "read_metrics"}),
    forbidden_actions=_COMMON_FORBIDDEN_ACTIONS
    | frozenset(
        {
            "send_email",
            "sales.send_outreach",
            "finance.record_cost",
            "modify_financial_records",
            "database.mutate_outside_reports",
        }
    ),
    allowed_tools=frozenset({"database", "notification"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS | frozenset({"email", "payment", "browser"}),
    allowed_entities=frozenset({"business_report", "daily_metric", "notification_record"}),
    resource_scope=frozenset({"reports"}),
    expected_outputs=frozenset({"ReportRunResult"}),
    output_schema="ReportRunResult",
    limits=AgentLimits(maximum_runtime_seconds=300, maximum_retries=1),
)

MANAGER_AGENT_CONTRACT = AgentContract(
    agent_id="manager",
    version="1.0.0",
    name="Manager Agent",
    description="Coordinator — plans, delegates, verifies. Not a superuser.",
    responsibility="Understand goals, delegate, verify results, request approvals.",
    allowed_actions=frozenset(
        {
            "plan",
            "delegate",
            "verify",
            "retry_safe",
            "prioritize",
            "request_approval",
            "stop_on_limits",
            "recommend_strategy",
            "learning.evaluate_performance",
            "responses.monitor",
            "followup.process_due",
        }
    ),
    forbidden_actions=frozenset(
        {
            "execute_shell",
            "arbitrary_http",
            "arbitrary_sql",
            "mutate_agent_contract",
            "mutate_policy",
            "change_own_permissions",
            "grant_permissions",
            "bypass_approval",
            "approvals.resolve",
            "disable_safety",
            "finance.money_transfer",
            "finance.autonomous_payment",
            "legal.contract",
            "sales.send_outreach",  # must delegate; cannot call send tool directly as manager identity
        }
    ),
    allowed_tools=frozenset({"database", "delegation"}),
    forbidden_tools=_COMMON_FORBIDDEN_TOOLS
    | frozenset({"email", "payment", "browser", "search", "ai"}),
    allowed_entities=frozenset({"manager_run", "manager_task", "manager_decision", "approval"}),
    resource_scope=frozenset({"manager"}),
    expected_outputs=frozenset({"ManagerRunResult"}),
    output_schema="ManagerRunResult",
    limits=AgentLimits(
        maximum_runtime_seconds=1800,
        maximum_retries=3,
        maximum_tasks=40,
        maximum_cost=Decimal("5.00"),
    ),
    escalation_rules=(
        EscalationRule(
            trigger="red_action",
            action="request_approval",
            description="RED actions require human-only resolution.",
        ),
    ),
    user_facing_scope_message=(
        "The manager stopped because it attempted an action outside its authority. "
        "The owner remains the highest authority."
    ),
)

ALL_AGENT_CONTRACTS: tuple[AgentContract, ...] = (
    RESEARCH_AGENT_CONTRACT,
    SCORING_AGENT_CONTRACT,
    AUDIT_AGENT_CONTRACT,
    SALES_AGENT_CONTRACT,
    DELIVERY_AGENT_CONTRACT,
    FINANCE_AGENT_CONTRACT,
    REPORT_AGENT_CONTRACT,
    MANAGER_AGENT_CONTRACT,
)
