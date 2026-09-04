"""ApprovalPolicy — authoritative risk classification for all actions.

GREEN: automatic
YELLOW: approval required before agent execution
RED: human only (agents may never execute)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import RiskLevel


@dataclass(frozen=True, slots=True)
class PolicyEntry:
    action_type: str
    risk_level: RiskLevel
    description: str
    agent_executable: bool
    """False for RED (human-only) and for actions not implemented for agents."""


# Canonical action catalog. Unknown actions default to RED (fail closed).
POLICY_CATALOG: dict[str, PolicyEntry] = {
    # GREEN — automatic
    "research.discover_companies": PolicyEntry(
        "research.discover_companies",
        RiskLevel.GREEN,
        "Public web research",
        True,
    ),
    "scoring.score_companies": PolicyEntry(
        "scoring.score_companies",
        RiskLevel.GREEN,
        "Deterministic lead scoring",
        True,
    ),
    "audit.audit_digital_presence": PolicyEntry(
        "audit.audit_digital_presence",
        RiskLevel.GREEN,
        "Public digital-presence audit",
        True,
    ),
    "database.update": PolicyEntry(
        "database.update",
        RiskLevel.GREEN,
        "Internal database updates",
        True,
    ),
    "analysis.internal": PolicyEntry(
        "analysis.internal",
        RiskLevel.GREEN,
        "Internal analysis",
        True,
    ),
    "report.generate": PolicyEntry(
        "report.generate",
        RiskLevel.GREEN,
        "Internal reports",
        True,
    ),
    "sales.draft_outreach": PolicyEntry(
        "sales.draft_outreach",
        RiskLevel.GREEN,
        "Draft sales outreach (no send)",
        True,
    ),
    "delivery.create_project": PolicyEntry(
        "delivery.create_project",
        RiskLevel.GREEN,
        "Create customer delivery project",
        True,
    ),
    "delivery.create_tasks": PolicyEntry(
        "delivery.create_tasks",
        RiskLevel.GREEN,
        "Create delivery project tasks",
        True,
    ),
    "delivery.execute_safe_task": PolicyEntry(
        "delivery.execute_safe_task",
        RiskLevel.GREEN,
        "Execute a non-sensitive delivery task",
        True,
    ),
    "delivery.verify_task": PolicyEntry(
        "delivery.verify_task",
        RiskLevel.GREEN,
        "Verify a delivery task before completion",
        True,
    ),
    "delivery.produce_deliverable": PolicyEntry(
        "delivery.produce_deliverable",
        RiskLevel.GREEN,
        "Produce an internal delivery artifact",
        True,
    ),
    "delivery.verify_project": PolicyEntry(
        "delivery.verify_project",
        RiskLevel.GREEN,
        "Verify a delivery project before completion",
        True,
    ),
    "delivery.complete_project": PolicyEntry(
        "delivery.complete_project",
        RiskLevel.GREEN,
        "Complete a verified delivery project",
        True,
    ),
    "finance.record_cost": PolicyEntry(
        "finance.record_cost",
        RiskLevel.GREEN,
        "Record an operational cost entry",
        True,
    ),
    "finance.record_revenue": PolicyEntry(
        "finance.record_revenue",
        RiskLevel.GREEN,
        "Record a revenue entry",
        True,
    ),
    "finance.calculate_metrics": PolicyEntry(
        "finance.calculate_metrics",
        RiskLevel.GREEN,
        "Calculate deterministic financial metrics",
        True,
    ),
    "finance.report": PolicyEntry(
        "finance.report",
        RiskLevel.GREEN,
        "Generate financial report from ledger",
        True,
    ),
    "followup.process_due": PolicyEntry(
        "followup.process_due",
        RiskLevel.GREEN,
        "Process due follow-ups (draft + approval request; no auto-send)",
        True,
    ),
    "responses.monitor": PolicyEntry(
        "responses.monitor",
        RiskLevel.GREEN,
        "Monitor response signals and stop rules from stored state",
        True,
    ),
    "learning.evaluate_performance": PolicyEntry(
        "learning.evaluate_performance",
        RiskLevel.GREEN,
        "Evaluate cycle performance and recommend next strategy",
        True,
    ),
    # YELLOW — approval required
    "delivery.execute_sensitive_task": PolicyEntry(
        "delivery.execute_sensitive_task",
        RiskLevel.YELLOW,
        "Execute a sensitive customer-facing delivery task",
        True,
    ),
    "sales.first_outreach": PolicyEntry(
        "sales.first_outreach",
        RiskLevel.YELLOW,
        "First outreach to a prospect",
        True,
    ),
    "sales.send_outreach": PolicyEntry(
        "sales.send_outreach",
        RiskLevel.YELLOW,
        "Outbound sales messaging",
        True,
    ),
    "sales.send_followup": PolicyEntry(
        "sales.send_followup",
        RiskLevel.YELLOW,
        "Outbound sales follow-up messaging",
        True,
    ),
    "commerce.discount": PolicyEntry(
        "commerce.discount",
        RiskLevel.YELLOW,
        "Offer a discount",
        True,
    ),
    "commerce.purchase": PolicyEntry(
        "commerce.purchase",
        RiskLevel.YELLOW,
        "Purchase goods or services",
        True,
    ),
    "tools.paid": PolicyEntry(
        "tools.paid",
        RiskLevel.YELLOW,
        "Enable or buy paid tools",
        True,
    ),
    "strategy.major_change": PolicyEntry(
        "strategy.major_change",
        RiskLevel.YELLOW,
        "Major strategy change",
        True,
    ),
    # RED — human only
    "finance.money_transfer": PolicyEntry(
        "finance.money_transfer",
        RiskLevel.RED,
        "Money transfer",
        False,
    ),
    "finance.autonomous_payment": PolicyEntry(
        "finance.autonomous_payment",
        RiskLevel.RED,
        "Autonomous payment",
        False,
    ),
    "legal.commitment": PolicyEntry(
        "legal.commitment",
        RiskLevel.RED,
        "Legal commitment",
        False,
    ),
    "legal.contract": PolicyEntry(
        "legal.contract",
        RiskLevel.RED,
        "Contract execution",
        False,
    ),
    "action.irreversible_high_impact": PolicyEntry(
        "action.irreversible_high_impact",
        RiskLevel.RED,
        "Irreversible high-impact action",
        False,
    ),
    "voice.voice_call": PolicyEntry(
        "voice.voice_call",
        RiskLevel.RED,
        "Voice call",
        False,
    ),
}


def normalize_action_type(action_type: str) -> str:
    cleaned = action_type.strip().lower().replace(":", ".")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return cleaned


def action_type_for_agent(agent_name: str, task_type: str) -> str:
    return normalize_action_type(f"{agent_name}.{task_type}")


class ApprovalPolicy:
    """Classifies actions and decides whether agents may execute them."""

    def __init__(self, catalog: dict[str, PolicyEntry] | None = None) -> None:
        self._catalog = catalog or POLICY_CATALOG

    def get_entry(self, action_type: str) -> PolicyEntry:
        key = normalize_action_type(action_type)
        entry = self._catalog.get(key)
        if entry is not None:
            return entry
        # Fail closed: unknown actions are RED / human-only
        return PolicyEntry(
            action_type=key,
            risk_level=RiskLevel.RED,
            description="Unknown action — fail closed",
            agent_executable=False,
        )

    def classify(self, action_type: str) -> RiskLevel:
        return self.get_entry(action_type).risk_level

    def is_automatic(self, action_type: str) -> bool:
        return self.classify(action_type) == RiskLevel.GREEN

    def requires_approval(self, action_type: str) -> bool:
        level = self.classify(action_type)
        return level in {RiskLevel.YELLOW, RiskLevel.RED}

    def is_human_only(self, action_type: str) -> bool:
        return self.classify(action_type) == RiskLevel.RED

    def agent_may_execute_when_approved(self, action_type: str) -> bool:
        entry = self.get_entry(action_type)
        return entry.agent_executable and entry.risk_level != RiskLevel.RED
