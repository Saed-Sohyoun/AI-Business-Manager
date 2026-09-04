"""Canonical action identifiers — single source aligned with POLICY_CATALOG.

Do not invent parallel names for the same action. Drift is tested in
``tests/test_policy_catalog_drift.py``.
"""

from __future__ import annotations

# Canonical action_type strings (agent.task form)
CANONICAL_ACTIONS: frozenset[str] = frozenset(
    {
        # GREEN
        "research.discover_companies",
        "scoring.score_companies",
        "audit.audit_digital_presence",
        "database.update",
        "analysis.internal",
        "report.generate",
        "sales.draft_outreach",
        "delivery.create_project",
        "delivery.create_tasks",
        "delivery.execute_safe_task",
        "delivery.verify_task",
        "delivery.produce_deliverable",
        "delivery.verify_project",
        "delivery.complete_project",
        "finance.record_cost",
        "finance.record_revenue",
        "finance.calculate_metrics",
        "finance.report",
        "followup.process_due",
        "responses.monitor",
        "learning.evaluate_performance",
        # YELLOW
        "delivery.execute_sensitive_task",
        "sales.first_outreach",
        "sales.send_outreach",
        "sales.send_followup",
        "commerce.discount",
        "commerce.purchase",
        "tools.paid",
        "strategy.major_change",
        # RED
        "finance.money_transfer",
        "finance.autonomous_payment",
        "legal.commitment",
        "legal.contract",
        "action.irreversible_high_impact",
        "voice.voice_call",
    }
)
