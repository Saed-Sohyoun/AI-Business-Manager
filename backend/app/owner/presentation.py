"""Human-friendly approval presentation for the owner control plane."""

from __future__ import annotations

from typing import Any

from app.approvals.schemas import ApprovalView
from app.models.enums import ApprovalStatus, RiskLevel
from app.owner.schemas import ApprovalAdvancedDetails, ApprovalDecisionView

_ACTION_TITLES: dict[str, str] = {
    "sales.send_outreach": "Send outreach email",
    "sales.send_follow_up": "Send follow-up email",
    "sales.draft_outreach": "Review outreach draft",
}

_REVERSIBILITY: dict[str, str] = {
    RiskLevel.GREEN.value: "Easily reversible",
    RiskLevel.YELLOW.value: "Partially reversible — review carefully",
    RiskLevel.RED.value: "Hard to reverse — human judgment required",
}


def present_approval(view: ApprovalView) -> ApprovalDecisionView:
    payload = view.action_payload or {}
    meta = view.metadata or {}
    risk = view.risk_level.value if isinstance(view.risk_level, RiskLevel) else str(view.risk_level)
    status = view.status.value if isinstance(view.status, ApprovalStatus) else str(view.status)
    title = _ACTION_TITLES.get(view.action_type, _humanize_action(view.action_type))
    affected = _affected_party(payload)
    why = str(meta.get("why") or meta.get("rationale") or view.description)
    benefit = meta.get("expected_benefit")
    cost = meta.get("estimated_cost") or payload.get("estimated_cost")
    recommended = "Approve if the benefit outweighs the risk" if status == "pending" else status.replace("_", " ")

    return ApprovalDecisionView(
        id=view.id,
        title=title,
        summary=view.description,
        why=why[:2000],
        affected_party=affected,
        expected_benefit=str(benefit) if benefit is not None else None,
        estimated_cost=str(cost) if cost is not None else None,
        risk=risk,
        reversibility=_REVERSIBILITY.get(risk, "Review carefully"),
        expires_at=view.expires_at,
        status=status,
        recommended_action=recommended,
        advanced_details=ApprovalAdvancedDetails(
            requesting_agent=view.requested_by,
            action_id=view.action_type,
            execution_id=str(view.agent_run_id) if view.agent_run_id else None,
            policy_level=risk,
            fingerprint=view.fingerprint,
            contract_version=str(meta.get("contract_version")) if meta.get("contract_version") else None,
            manager_run_id=str(view.manager_run_id) if view.manager_run_id else None,
            manager_task_id=str(view.manager_task_id) if view.manager_task_id else None,
            agent_run_id=str(view.agent_run_id) if view.agent_run_id else None,
        ),
        resolved_by=view.resolved_by,
        resolved_at=view.resolved_at,
        resolution_note=view.resolution_note,
    )


def _humanize_action(action_type: str) -> str:
    parts = action_type.replace(".", " ").replace("_", " ").strip()
    return parts[:1].upper() + parts[1:] if parts else "Pending decision"


def _affected_party(payload: dict[str, Any]) -> str | None:
    for key in ("recipient_email", "to_email", "company_name", "company", "lead_name"):
        val = payload.get(key)
        if val:
            return str(val)
    return None
