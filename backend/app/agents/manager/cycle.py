"""Business-cycle goal parsing, learning recommendations, and safe stop helpers.

Phase 19 — connects the autonomous funnel under Manager without inventing metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.agents.manager.schemas import BusinessStateSnapshot


_MRR_RE = re.compile(
    r"(?:€|EUR|\$|USD)?\s*(?P<amount>\d+(?:[.,]\d+)?)\s*(?:€|EUR|\$|USD)?\s*MRR",
    re.IGNORECASE,
)
_COST_CAP_RE = re.compile(
    r"(?:costs?|operating costs?|opex)\s*(?:below|under|<|<=)\s*"
    r"(?:€|EUR|\$|USD)?\s*(?P<amount>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_LEADS_RE = re.compile(
    r"(?P<count>\d+)\s+(?:qualified\s+)?(?:local\s+)?(?:business\s+)?leads?",
    re.IGNORECASE,
)


def _parse_money(raw: str) -> Decimal:
    cleaned = raw.strip()
    if not cleaned:
        return Decimal("0")
    if "," in cleaned and "." in cleaned:
        # 1,000.50 (US) vs 1.000,50 (EU)
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        # 1,000 / 1,000,000 → thousands; 1,5 → decimal
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].replace(" ", "").isdigit():
            cleaned = "".join(parts)
        elif all(len(p) == 3 for p in parts[1:]) and parts[0].isdigit():
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


@dataclass(frozen=True, slots=True)
class CycleGoal:
    """Parsed business objective for the Manager planner."""

    target_qualified_leads: int
    target_mrr: Decimal | None
    max_monthly_operating_cost: Decimal | None
    full_cycle: bool
    currency_hint: str  # EUR | USD | UNKNOWN


def parse_cycle_goal(
    goal: str,
    *,
    explicit_leads: int | None = None,
    explicit_mrr: Decimal | None = None,
    explicit_cost_cap: Decimal | None = None,
    force_full_cycle: bool = False,
) -> CycleGoal:
    goal_l = goal.lower()
    mrr_match = _MRR_RE.search(goal)
    cost_match = _COST_CAP_RE.search(goal)
    leads_match = _LEADS_RE.search(goal)

    target_mrr = explicit_mrr
    if target_mrr is None and mrr_match:
        target_mrr = _parse_money(mrr_match.group("amount"))

    cost_cap = explicit_cost_cap
    if cost_cap is None and cost_match:
        cost_cap = _parse_money(cost_match.group("amount"))

    if explicit_leads is not None:
        leads = max(1, min(explicit_leads, 500))
    elif leads_match:
        leads = max(1, min(int(leads_match.group("count")), 500))
    elif target_mrr is not None:
        # MRR goals still need a pipeline floor for research/scoring.
        leads = 10
    else:
        leads = 10

    currency = "UNKNOWN"
    if "€" in goal or "eur" in goal_l:
        currency = "EUR"
    elif "$" in goal or "usd" in goal_l:
        currency = "USD"

    full = bool(
        force_full_cycle
        or target_mrr is not None
        or cost_cap is not None
        or any(
            token in goal_l
            for token in (
                "full cycle",
                "business cycle",
                "autonomous",
                "mrr",
                "revenue",
                "roi",
                "customer",
                "delivery",
                "outreach",
                "follow-up",
                "follow up",
            )
        )
    )

    return CycleGoal(
        target_qualified_leads=leads,
        target_mrr=target_mrr,
        max_monthly_operating_cost=cost_cap,
        full_cycle=full,
        currency_hint=currency,
    )


def evaluate_goal_met(goal: CycleGoal, state: BusinessStateSnapshot) -> tuple[bool, str]:
    """Return (met, rationale). Never invents numbers — uses inspected state only."""
    parts: list[str] = []
    met = True

    if goal.target_qualified_leads:
        ok = state.qualified_leads >= goal.target_qualified_leads
        parts.append(
            f"qualified_leads={state.qualified_leads}/{goal.target_qualified_leads} "
            f"({'ok' if ok else 'gap'})"
        )
        # Lead target alone is enough for lead-only goals.
        if not goal.full_cycle and not goal.target_mrr:
            return ok, "; ".join(parts)
        if goal.target_mrr is None and goal.max_monthly_operating_cost is None:
            # Full cycle without money targets: pipeline floor still applies.
            met = ok and met

    if goal.target_mrr is not None:
        ok = state.mrr >= goal.target_mrr
        parts.append(f"mrr={state.mrr}/{goal.target_mrr} ({'ok' if ok else 'gap'})")
        met = met and ok

    if goal.max_monthly_operating_cost is not None:
        ok = state.operating_costs_mtd <= goal.max_monthly_operating_cost
        parts.append(
            f"costs={state.operating_costs_mtd}/{goal.max_monthly_operating_cost} "
            f"({'ok' if ok else 'over'})"
        )
        met = met and ok

    if goal.target_mrr is None and goal.max_monthly_operating_cost is None and goal.full_cycle:
        # Full cycle without explicit money: require lead floor only.
        met = state.qualified_leads >= goal.target_qualified_leads
        parts.append("full_cycle_without_money_targets")

    return met, "; ".join(parts) if parts else "no_targets"


def cost_cap_blocks_outbound(goal: CycleGoal, state: BusinessStateSnapshot) -> bool:
    if goal.max_monthly_operating_cost is None:
        return False
    return state.operating_costs_mtd >= goal.max_monthly_operating_cost


def recommend_next_strategy(
    *,
    goal: CycleGoal,
    state: BusinessStateSnapshot,
    task_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministic learning / next-decision recommendations from real state."""
    recommendations: list[str] = []
    priorities: list[str] = []

    met, rationale = evaluate_goal_met(goal, state)
    gap_leads = max(0, goal.target_qualified_leads - state.qualified_leads)

    if gap_leads > 0:
        priorities.append("pipeline")
        recommendations.append(
            f"Need {gap_leads} more qualified leads; continue research → score → audit."
        )
    if state.qualified_unaudited_count > 0:
        priorities.append("audit")
        recommendations.append(
            f"Audit {min(state.qualified_unaudited_count, 5)} qualified companies lacking audits."
        )
    if state.draftable_leads_count > 0 and state.pending_outreach_drafts == 0:
        priorities.append("sales_draft")
        recommendations.append("Draft outreach for qualified leads with contact email.")
    if state.pending_outreach_drafts > 0:
        priorities.append("approval")
        recommendations.append(
            f"{state.pending_outreach_drafts} draft outreach(es) await human approval before send."
        )
    if state.pending_approvals > 0:
        priorities.append("approvals_queue")
        recommendations.append(
            f"{state.pending_approvals} approval(s) pending — Manager will not bypass."
        )
    if state.follow_ups_due > 0:
        priorities.append("follow_ups")
        recommendations.append(f"Process {state.follow_ups_due} due follow-up sequence(s).")
    if state.converted_leads_without_project > 0:
        priorities.append("delivery")
        recommendations.append("Start delivery projects for converted leads without projects.")
    if goal.target_mrr is not None and state.mrr < goal.target_mrr:
        priorities.append("revenue")
        recommendations.append(
            f"MRR gap {goal.target_mrr - state.mrr}; focus delivery completion and recurring revenue."
        )
    if goal.max_monthly_operating_cost is not None and state.operating_costs_mtd > goal.max_monthly_operating_cost:
        priorities.append("cost_control")
        recommendations.append("Operating costs exceed cap — pause paid tools and outbound spend.")
    if not recommendations:
        recommendations.append("Hold steady; re-measure on next scheduled cycle.")
        priorities.append("maintain")

    return {
        "goal_met": met,
        "rationale": rationale,
        "priorities": priorities[:8],
        "recommendations": recommendations[:8],
        "state_summary": {
            "qualified_leads": state.qualified_leads,
            "mrr": str(state.mrr),
            "operating_costs_mtd": str(state.operating_costs_mtd),
            "profit_mtd": str(state.profit_mtd),
            "pending_approvals": state.pending_approvals,
            "customers": state.customers_active,
        },
        "task_results_seen": len(task_results or []),
        "major_strategy_change_required": bool(
            goal.target_mrr is not None
            and state.mrr < (goal.target_mrr * Decimal("0.25"))
            and state.qualified_leads == 0
            and state.companies_total > 0
        ),
    }


# Hard safety: max planned tasks in a single Manager plan (in addition to settings.max_tasks_per_run).
MAX_PLAN_TASKS = 12
MAX_DRAFTS_PER_PLAN = 2
MAX_SENDS_PER_PLAN = 1
MAX_DELIVERY_PROJECTS_PER_PLAN = 1
MAX_AUDITS_IN_FULL_CYCLE = 5
