"""Agent permissions — thin registry aligned with ApprovalPolicy.

Risk classification and execution gates live in ApprovalPolicy / ApprovalService.
This module only answers “is this a known manager-delegable task?”.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.approvals.policy import ApprovalPolicy, action_type_for_agent
from app.models.enums import RiskLevel


@dataclass(frozen=True, slots=True)
class AgentPermission:
    agent_name: str
    task_type: str
    risk_level: RiskLevel
    allowed: bool
    description: str
    action_type: str


_POLICY = ApprovalPolicy()

# Explicit manager-delegable allow-list (unknown pairs are invalid tasks).
_DELEGABLE: dict[tuple[str, str], str] = {
    ("research", "discover_companies"): "Public web research; no outbound contact.",
    ("scoring", "score_companies"): "Deterministic internal lead scoring.",
    ("audit", "audit_digital_presence"): "Public digital-presence audit; no outreach.",
    ("sales", "draft_outreach"): "Draft personalized outreach — no send.",
    ("sales", "first_outreach"): "First outreach — YELLOW, requires approval.",
    ("sales", "send_outreach"): "Outbound sales messaging — YELLOW, requires approval.",
    ("sales", "send_followup"): "Outbound sales follow-up — YELLOW, requires approval.",
    ("delivery", "create_project"): "Create delivery project — GREEN.",
    ("delivery", "create_tasks"): "Create delivery tasks — GREEN.",
    ("delivery", "execute_safe_task"): "Execute safe delivery task — GREEN.",
    ("delivery", "execute_sensitive_task"): "Sensitive delivery task — YELLOW, requires approval.",
    ("delivery", "verify_task"): "Verify delivery task — GREEN.",
    ("delivery", "produce_deliverable"): "Produce deliverable — GREEN.",
    ("delivery", "verify_project"): "Verify delivery project — GREEN.",
    ("delivery", "complete_project"): "Complete verified project — GREEN.",
    ("finance", "record_cost"): "Record cost entry — GREEN.",
    ("finance", "record_revenue"): "Record revenue entry — GREEN.",
    ("finance", "calculate_metrics"): "Calculate financial metrics.",
    ("finance", "report"): "Financial report from ledger — GREEN.",
    ("report", "generate"): "Generate CEO business report — GREEN.",
    ("followup", "process_due"): "Process due follow-ups (draft + approval request).",
    ("responses", "monitor"): "Monitor response signals from lead/follow-up state.",
    ("learning", "evaluate_performance"): "Evaluate cycle performance; recommend next strategy.",
    ("commerce", "discount"): "Discount offer — YELLOW, requires approval.",
    ("commerce", "purchase"): "Purchase — YELLOW, requires approval.",
    ("tools", "paid"): "Paid tool — YELLOW, requires approval.",
    ("strategy", "major_change"): "Major strategy change — YELLOW, requires approval.",
    ("finance", "money_transfer"): "Money transfer — RED, human only.",
    ("finance", "autonomous_payment"): "Autonomous payment — RED, human only.",
    ("legal", "commitment"): "Legal commitment — RED, human only.",
    ("legal", "contract"): "Contract — RED, human only.",
    ("action", "irreversible_high_impact"): "Irreversible high-impact — RED, human only.",
    ("voice", "voice_call"): "Voice call — RED, human only.",
}


def get_permission(agent_name: str, task_type: str) -> AgentPermission | None:
    key = (agent_name.strip().lower(), task_type.strip().lower())
    description = _DELEGABLE.get(key)
    if description is None:
        return None
    action_type = action_type_for_agent(key[0], key[1])
    entry = _POLICY.get_entry(action_type)
    return AgentPermission(
        agent_name=key[0],
        task_type=key[1],
        risk_level=entry.risk_level,
        allowed=entry.agent_executable,
        description=description,
        action_type=action_type,
    )


def requires_approval(permission: AgentPermission, *, approval_required_for_external: bool) -> bool:
    """Legacy helper — prefer ApprovalService.evaluate_gate."""
    if permission.risk_level == RiskLevel.GREEN:
        return False
    if permission.risk_level == RiskLevel.RED:
        return True
    if permission.risk_level == RiskLevel.YELLOW:
        return bool(approval_required_for_external)
    return True
