"""Verify delegated task outcomes against expected contracts."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.manager.schemas import DelegationResult


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    ok: bool
    notes: str


def verify_delegation(
    *,
    agent_name: str,
    task_type: str,
    result: DelegationResult,
) -> VerificationOutcome:
    if result.status == "timeout":
        return VerificationOutcome(False, "timeout_reported")
    if result.status == "failed":
        return VerificationOutcome(False, result.error_message or "failed_without_error")
    if not result.summary.strip():
        return VerificationOutcome(False, "empty_summary")

    if agent_name == "research" and task_type == "discover_companies":
        if result.status == "succeeded" and "companies_created" not in result.output:
            return VerificationOutcome(False, "missing_companies_created")
        return VerificationOutcome(True, "research_ok")

    if agent_name == "scoring" and task_type == "score_companies":
        if "scored_count" not in result.output and result.status == "succeeded":
            return VerificationOutcome(False, "missing_scored_count")
        return VerificationOutcome(True, "scoring_ok")

    if agent_name == "audit" and task_type == "audit_digital_presence":
        if "audits_completed" not in result.output and result.status == "succeeded":
            return VerificationOutcome(False, "missing_audits_completed")
        return VerificationOutcome(True, "audit_ok")

    if agent_name == "sales" and task_type == "draft_outreach":
        if result.status == "succeeded" and "outreach_id" not in result.output:
            return VerificationOutcome(False, "missing_outreach_id")
        return VerificationOutcome(True, "draft_ok")

    if agent_name == "sales" and task_type in {"send_outreach", "first_outreach", "send_followup"}:
        return VerificationOutcome(result.status in {"succeeded", "partial"}, "outreach_send_ok")

    if agent_name == "followup" and task_type == "process_due":
        if "processed" not in result.output and result.status == "succeeded":
            return VerificationOutcome(False, "missing_processed_count")
        return VerificationOutcome(True, "followup_ok")

    if agent_name == "responses" and task_type == "monitor":
        if "responses_recorded" not in result.output and result.status == "succeeded":
            return VerificationOutcome(False, "missing_responses_recorded")
        return VerificationOutcome(True, "responses_ok")

    if agent_name == "delivery" and task_type == "create_project":
        if result.status == "succeeded" and "project_id" not in result.output:
            return VerificationOutcome(False, "missing_project_id")
        return VerificationOutcome(True, "delivery_ok")

    if agent_name == "finance" and task_type == "calculate_metrics":
        if result.status == "succeeded" and "metric_id" not in result.output and "profit" not in result.output:
            return VerificationOutcome(False, "missing_finance_metrics")
        return VerificationOutcome(True, "finance_ok")

    if agent_name == "report" and task_type == "generate":
        if result.status == "succeeded" and "report_id" not in result.output:
            return VerificationOutcome(False, "missing_report_id")
        return VerificationOutcome(True, "report_ok")

    if agent_name == "learning" and task_type == "evaluate_performance":
        if "recommendations" not in result.output and result.status == "succeeded":
            return VerificationOutcome(False, "missing_recommendations")
        return VerificationOutcome(True, "learning_ok")

    if agent_name == "strategy" and task_type == "major_change":
        return VerificationOutcome(result.status in {"succeeded", "partial"}, "strategy_ok")

    # Unknown but executed — require non-failed status only
    return VerificationOutcome(result.status in {"succeeded", "partial"}, "generic_ok")
