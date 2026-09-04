"""Deterministic planner — full autonomous business cycle under Manager.

Stages (state-gated, capped — never infinite):
  research → score → audit → sales draft → outreach approval/send →
  follow-ups → delivery → finance → report → learning / next decision

YELLOW outbound stops for human approval. RED is never planned.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.manager.cycle import (
    MAX_AUDITS_IN_FULL_CYCLE,
    MAX_DELIVERY_PROJECTS_PER_PLAN,
    MAX_DRAFTS_PER_PLAN,
    MAX_PLAN_TASKS,
    MAX_SENDS_PER_PLAN,
    cost_cap_blocks_outbound,
    parse_cycle_goal,
)
from app.agents.manager.schemas import BusinessStateSnapshot, ManagerRequest, PlannedTaskSpec
from app.config import Settings


@dataclass(frozen=True, slots=True)
class PlanResult:
    target_qualified_leads: int
    summary: str
    tasks: list[PlannedTaskSpec]
    industry: str | None
    location: str | None
    query: str
    target_mrr: str | None = None
    max_monthly_operating_cost: str | None = None
    full_cycle: bool = False


def parse_target_count(goal: str, explicit: int | None) -> int:
    return parse_cycle_goal(goal, explicit_leads=explicit).target_qualified_leads


def build_search_query(request: ManagerRequest, *, location: str | None, industry: str | None) -> str:
    if request.query:
        return request.query.strip()
    parts: list[str] = []
    if industry:
        parts.append(industry)
    parts.append("local businesses")
    if location:
        parts.append(location)
    parts.append("website")
    return " ".join(parts)


def _append(tasks: list[PlannedTaskSpec], spec: PlannedTaskSpec, *, limit: int) -> bool:
    if len(tasks) >= limit:
        return False
    tasks.append(spec)
    return True


def create_plan(
    request: ManagerRequest,
    state: BusinessStateSnapshot,
    settings: Settings,
) -> PlanResult:
    force_full = request.full_cycle if request.full_cycle is not None else bool(
        (request.metadata or {}).get("full_cycle")
    )
    cycle = parse_cycle_goal(
        request.goal,
        explicit_leads=request.target_qualified_leads,
        explicit_mrr=request.target_mrr,
        explicit_cost_cap=request.max_monthly_operating_cost,
        force_full_cycle=force_full,
    )
    industry = request.industry
    location = request.location
    query = build_search_query(request, location=location, industry=industry)
    target = cycle.target_qualified_leads
    gap = max(0, target - state.qualified_leads)
    goal_l = request.goal.lower()
    plan_limit = min(MAX_PLAN_TASKS, settings.max_tasks_per_run)
    tasks: list[PlannedTaskSpec] = []

    # --- Stage: RESEARCH ---
    if gap > 0 or state.companies_total == 0:
        research_max = min(
            max(gap, target, 1),
            settings.max_companies_per_run,
            settings.max_tasks_per_run,
        )
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="research",
                task_type="discover_companies",
                payload={
                    "query": query,
                    "industry": industry,
                    "location": location,
                    "max_companies": research_max,
                    "verify_with_browser": settings.research_verify_with_browser,
                },
                rationale=(
                    f"Need ~{gap} more qualified leads; discover public companies "
                    f"(cap={research_max})."
                ),
            ),
            limit=plan_limit,
        )

    # --- Stage: SCORE ---
    if state.unscored_company_ids or gap > 0:
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="scoring",
                task_type="score_companies",
                payload={
                    "company_ids": state.unscored_company_ids,
                    "score_all_unscored": True,
                    "limit": min(settings.max_companies_per_run, 50),
                },
                rationale="Score discovered/unscored companies with the deterministic engine.",
            ),
            limit=plan_limit,
        )

    # --- Stage: AUDIT ---
    want_audit = (
        cycle.full_cycle
        or state.qualified_unaudited_count > 0
        or any(token in goal_l for token in ("audit", "website quality", "digital presence"))
    )
    if want_audit and (state.unaudited_company_ids or gap > 0 or state.qualified_unaudited_count > 0):
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="audit",
                task_type="audit_digital_presence",
                payload={
                    "company_ids": state.unaudited_company_ids[:MAX_AUDITS_IN_FULL_CYCLE],
                    "max_audits": min(settings.max_audits_per_run, MAX_AUDITS_IN_FULL_CYCLE),
                    "use_ai": settings.audit_use_ai,
                },
                rationale="Audit digital presence for strategy and personalized outreach.",
            ),
            limit=plan_limit,
        )

    outbound_blocked = cost_cap_blocks_outbound(cycle, state)

    if cycle.full_cycle:
        # --- Stage: SALES DRAFT (GREEN) ---
        if not outbound_blocked:
            for item in state.draftable_leads[:MAX_DRAFTS_PER_PLAN]:
                added = _append(
                    tasks,
                    PlannedTaskSpec(
                        agent_name="sales",
                        task_type="draft_outreach",
                        payload={
                            "company_id": item["company_id"],
                            "lead_id": item["lead_id"],
                            "use_ai": settings.sales_use_ai,
                        },
                        rationale="Prepare outreach draft — no send without approval.",
                    ),
                    limit=plan_limit,
                )
                if not added:
                    break

        # --- Stage: OUTREACH SEND (YELLOW — stops for approval) ---
        # Prefer approved drafts; else queue one draft for approval gate.
        send_ids = list(state.approved_outreach_ids) + list(state.draft_outreach_ids)
        if not outbound_blocked:
            for oid in send_ids[:MAX_SENDS_PER_PLAN]:
                _append(
                    tasks,
                    PlannedTaskSpec(
                        agent_name="sales",
                        task_type="send_outreach",
                        payload={"outreach_id": oid},
                        rationale=(
                            "Execute approved outreach or request approval for draft "
                            "(never bypasses ApprovalService)."
                        ),
                    ),
                    limit=plan_limit,
                )

        # --- Stage: FOLLOW-UPS (draft + approval request only) ---
        if state.follow_ups_due > 0 and not outbound_blocked:
            _append(
                tasks,
                PlannedTaskSpec(
                    agent_name="followup",
                    task_type="process_due",
                    payload={"limit": min(state.follow_ups_due, settings.max_outbound_messages_per_day)},
                    rationale="Process due follow-up sequences (draft + approval; no auto-send).",
                ),
                limit=plan_limit,
            )

        # --- Stage: RESPONSE MONITOR ---
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="responses",
                task_type="monitor",
                payload={},
                rationale="Inspect response/stop-rule signals from lead and follow-up state.",
            ),
            limit=plan_limit,
        )

        # --- Stage: CUSTOMER / DELIVERY ---
        for lead_id in state.converted_lead_ids[:MAX_DELIVERY_PROJECTS_PER_PLAN]:
            _append(
                tasks,
                PlannedTaskSpec(
                    agent_name="delivery",
                    task_type="create_project",
                    payload={"lead_id": lead_id},
                    rationale="Convert lead → customer → delivery project with default tasks.",
                ),
                limit=plan_limit,
            )

        # --- Stage: FINANCE / ROI ---
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="finance",
                task_type="calculate_metrics",
                payload={
                    "currency": "EUR" if cycle.currency_hint == "EUR" else "USD",
                    "lead_count": state.companies_total,
                    "qualified_lead_count": state.qualified_leads,
                    "customer_count": state.customers_active,
                },
                rationale="Calculate revenue, cost, profit, and ROI from ledger facts.",
            ),
            limit=plan_limit,
        )

        # --- Stage: REPORT ---
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="report",
                task_type="generate",
                payload={"period_type": "daily", "currency": "EUR" if cycle.currency_hint == "EUR" else "USD"},
                rationale="Generate CEO report from real DB facts for learning and next decision.",
            ),
            limit=plan_limit,
        )

        # --- Stage: LEARNING / NEXT DECISION ---
        _append(
            tasks,
            PlannedTaskSpec(
                agent_name="learning",
                task_type="evaluate_performance",
                payload={
                    "target_qualified_leads": target,
                    "target_mrr": str(cycle.target_mrr) if cycle.target_mrr is not None else None,
                    "max_monthly_operating_cost": (
                        str(cycle.max_monthly_operating_cost)
                        if cycle.max_monthly_operating_cost is not None
                        else None
                    ),
                },
                rationale="Evaluate cycle performance and recommend next strategy (traceable).",
            ),
            limit=plan_limit,
        )

        # Optional YELLOW strategy stop when learning would flag major change —
        # planned only when pipeline is empty despite companies (human gate).
        if (
            cycle.target_mrr is not None
            and state.mrr < cycle.target_mrr
            and state.qualified_leads == 0
            and state.companies_total > 0
            and state.draftable_leads_count == 0
        ):
            _append(
                tasks,
                PlannedTaskSpec(
                    agent_name="strategy",
                    task_type="major_change",
                    payload={
                        "reason": "mrr_gap_with_stalled_pipeline",
                        "target_mrr": str(cycle.target_mrr),
                        "measured_mrr": str(state.mrr),
                    },
                    rationale="Major strategy change requires human approval (YELLOW).",
                ),
                limit=plan_limit,
            )

    if not tasks:
        summary = (
            f"Goal already met or no actionable work: qualified={state.qualified_leads} "
            f"target={target} mrr={state.mrr}."
        )
    else:
        agents = ", ".join(f"{t.agent_name}/{t.task_type}" for t in tasks)
        summary = (
            f"Cycle plan target_leads={target} full_cycle={cycle.full_cycle} "
            f"(qualified={state.qualified_leads}, mrr={state.mrr}): {agents}."
        )
        if outbound_blocked:
            summary += " Outbound paused: operating cost cap reached."

    return PlanResult(
        target_qualified_leads=target,
        summary=summary,
        tasks=tasks,
        industry=industry,
        location=location,
        query=query,
        target_mrr=str(cycle.target_mrr) if cycle.target_mrr is not None else None,
        max_monthly_operating_cost=(
            str(cycle.max_monthly_operating_cost)
            if cycle.max_monthly_operating_cost is not None
            else None
        ),
        full_cycle=cycle.full_cycle,
    )
