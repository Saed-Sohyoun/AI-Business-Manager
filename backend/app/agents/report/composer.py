"""Compose CEO report sections from ReportFacts — no fabricated metrics."""

from __future__ import annotations

from typing import Any

from app.agents.report.collector import ReportFacts
from app.models.enums import ReportStatementKind

SECTION_SPECS: list[tuple[str, str]] = [
    ("business_goal", "Business Goal"),
    ("progress", "Progress"),
    ("companies_researched", "Companies Researched"),
    ("qualified_leads", "Qualified Leads"),
    ("audits", "Audits"),
    ("outreach", "Outreach"),
    ("replies", "Replies"),
    ("meetings", "Meetings"),
    ("customers", "Customers"),
    ("revenue", "Revenue"),
    ("costs", "Costs"),
    ("profit", "Profit"),
    ("roi", "ROI"),
    ("best_opportunities", "Best Opportunities"),
    ("problems", "Problems"),
    ("what_worked", "What Worked"),
    ("what_failed", "What Failed"),
    ("strategy_recommendations", "Strategy Recommendations"),
    ("approvals_needed", "Approvals Needed"),
    ("tomorrows_priorities", "Tomorrow's Priorities"),
]


def _stmt(
    kind: ReportStatementKind,
    text: str,
    *,
    value: str | None = None,
    available: bool = True,
) -> dict[str, Any]:
    return {
        "kind": kind.value,
        "text": text,
        "value": value,
        "available": available,
    }


def _unavailable(metric_name: str) -> dict[str, Any]:
    return _stmt(
        ReportStatementKind.UNAVAILABLE,
        f"{metric_name} is unavailable — no matching database records for this period.",
        available=False,
    )


def compose_sections(facts: ReportFacts) -> list[dict[str, Any]]:
    builders = {
        "business_goal": _section_business_goal,
        "progress": _section_progress,
        "companies_researched": _section_companies,
        "qualified_leads": _section_qualified,
        "audits": _section_audits,
        "outreach": _section_outreach,
        "replies": _section_replies,
        "meetings": _section_meetings,
        "customers": _section_customers,
        "revenue": _section_revenue,
        "costs": _section_costs,
        "profit": _section_profit,
        "roi": _section_roi,
        "best_opportunities": _section_opportunities,
        "problems": _section_problems,
        "what_worked": _section_worked,
        "what_failed": _section_failed,
        "strategy_recommendations": _section_strategy,
        "approvals_needed": _section_approvals,
        "tomorrows_priorities": _section_priorities,
    }
    sections: list[dict[str, Any]] = []
    for order, (section_id, title) in enumerate(SECTION_SPECS, start=1):
        statements = builders[section_id](facts)
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "order": order,
                "statements": statements,
            }
        )
    return sections


def _section_business_goal(facts: ReportFacts) -> list[dict[str, Any]]:
    if facts.latest_goal:
        stmts = [
            _stmt(
                ReportStatementKind.FACT,
                f"Latest recorded business goal: {facts.latest_goal}",
                value=facts.latest_goal,
            )
        ]
        if facts.target_qualified_leads is not None:
            stmts.append(
                _stmt(
                    ReportStatementKind.FACT,
                    f"Target qualified leads: {facts.target_qualified_leads}",
                    value=str(facts.target_qualified_leads),
                )
            )
        stmts.append(
            _stmt(
                ReportStatementKind.INTERPRETATION,
                "Goal text is taken from the most relevant ManagerRun record; it is not inferred.",
            )
        )
        return stmts
    return [_unavailable("Business goal")]


def _section_progress(facts: ReportFacts) -> list[dict[str, Any]]:
    stmts = [
        _stmt(
            ReportStatementKind.FACT,
            f"Manager runs started in period: {facts.manager_runs_in_period}",
            value=str(facts.manager_runs_in_period),
        )
    ]
    if facts.measured_qualified_leads is not None and facts.target_qualified_leads is not None:
        stmts.append(
            _stmt(
                ReportStatementKind.FACT,
                (
                    f"Measured qualified leads {facts.measured_qualified_leads} "
                    f"vs target {facts.target_qualified_leads}"
                ),
                value=f"{facts.measured_qualified_leads}/{facts.target_qualified_leads}",
            )
        )
        if facts.target_qualified_leads > 0:
            ratio = facts.measured_qualified_leads / facts.target_qualified_leads
            if ratio >= 1:
                stmts.append(
                    _stmt(
                        ReportStatementKind.INTERPRETATION,
                        "Qualified-lead target has been met or exceeded based on measured counts.",
                    )
                )
            else:
                stmts.append(
                    _stmt(
                        ReportStatementKind.INTERPRETATION,
                        "Qualified-lead target has not yet been met based on measured counts.",
                    )
                )
    elif facts.latest_goal is None and facts.manager_runs_in_period == 0:
        stmts.append(_unavailable("Goal progress (no manager runs in period)"))
    return stmts


def _section_companies(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Companies created in period: {facts.companies_researched}",
            value=str(facts.companies_researched),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Companies in database (all-time): {facts.companies_total}",
            value=str(facts.companies_total),
        ),
        _stmt(
            ReportStatementKind.INTERPRETATION,
            (
                "Period research volume is based on Company.created_at within the report window."
                if facts.companies_researched or facts.companies_total
                else "No company records exist yet."
            ),
        ),
    ]


def _section_qualified(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            (
                f"Qualified leads (companies with GOOD/HIGH score band): "
                f"{facts.qualified_leads}"
            ),
            value=str(facts.qualified_leads),
        ),
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "Qualification uses stored CompanyScore bands only — scores are not estimated in this report.",
        ),
    ]


def _section_audits(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Audits completed in period: {facts.audits_in_period}",
            value=str(facts.audits_in_period),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Audits total: {facts.audits_total}",
            value=str(facts.audits_total),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"High/critical priority audits (all-time): {facts.high_priority_audits}",
            value=str(facts.high_priority_audits),
        ),
    ]


def _section_outreach(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Outreach drafts in period: {facts.outreach_drafted}",
            value=str(facts.outreach_drafted),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Outreach marked sent in period: {facts.outreach_sent}",
            value=str(facts.outreach_sent),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Outbound messages sent in period: {facts.outbound_sent}",
            value=str(facts.outbound_sent),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Follow-up messages sent in period: {facts.outbound_followups_sent}",
            value=str(facts.outbound_followups_sent),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Outreach failures in period: {facts.outreach_failed}",
            value=str(facts.outreach_failed),
        ),
    ]


def _section_replies(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Leads with replies recorded in period: {facts.replies}",
            value=str(facts.replies),
        )
    ]


def _section_meetings(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Meetings generated (from follow-up sequences) in period: {facts.meetings}",
            value=str(facts.meetings),
        )
    ]


def _section_customers(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Customers converted in period: {facts.customers_converted}",
            value=str(facts.customers_converted),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Customers total: {facts.customers_total}",
            value=str(facts.customers_total),
        ),
    ]


def _section_revenue(facts: ReportFacts) -> list[dict[str, Any]]:
    if not facts.revenue_available:
        return [_unavailable("Revenue")]
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Total revenue ({facts.currency}): {facts.total_revenue}",
            value=str(facts.total_revenue),
        ),
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "Revenue is summed from RevenueEntry rows in the period/currency — not estimated.",
        ),
    ]


def _section_costs(facts: ReportFacts) -> list[dict[str, Any]]:
    if not facts.costs_available:
        return [_unavailable("Costs")]
    stmts = [
        _stmt(
            ReportStatementKind.FACT,
            f"Total costs ({facts.currency}): {facts.total_costs}",
            value=str(facts.total_costs),
        )
    ]
    for cat, amount in sorted(facts.cost_breakdown.items()):
        stmts.append(
            _stmt(
                ReportStatementKind.FACT,
                f"Cost category {cat}: {amount} {facts.currency}",
                value=str(amount),
            )
        )
    stmts.append(
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "Costs are summed from CostEntry ledger rows — categories are not inferred beyond stored values.",
        )
    )
    return stmts


def _section_profit(facts: ReportFacts) -> list[dict[str, Any]]:
    if facts.gross_profit is None:
        return [_unavailable("Profit")]
    stmts = [
        _stmt(
            ReportStatementKind.FACT,
            f"Gross profit ({facts.currency}): {facts.gross_profit}",
            value=str(facts.gross_profit),
        )
    ]
    if facts.gross_profit > 0:
        stmts.append(
            _stmt(
                ReportStatementKind.INTERPRETATION,
                "Gross profit is positive for the recorded ledger activity in this period.",
            )
        )
    elif facts.gross_profit < 0:
        stmts.append(
            _stmt(
                ReportStatementKind.INTERPRETATION,
                "Gross profit is negative for the recorded ledger activity in this period.",
            )
        )
    else:
        stmts.append(
            _stmt(
                ReportStatementKind.INTERPRETATION,
                "Gross profit is zero for the recorded ledger activity in this period.",
            )
        )
    return stmts


def _section_roi(facts: ReportFacts) -> list[dict[str, Any]]:
    if facts.roi is None:
        if facts.costs_available and facts.total_costs == 0:
            return [
                _stmt(
                    ReportStatementKind.UNAVAILABLE,
                    "ROI is unavailable because total costs are zero (division undefined).",
                    available=False,
                )
            ]
        return [_unavailable("ROI")]
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"ROI ((revenue - costs) / costs): {facts.roi}",
            value=str(facts.roi),
        ),
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "ROI uses deterministic Decimal arithmetic on ledger totals only.",
        ),
    ]


def _section_opportunities(facts: ReportFacts) -> list[dict[str, Any]]:
    if not facts.best_opportunity_labels:
        return [_unavailable("Best opportunities (no HIGH-band company scores found)")]
    stmts = [
        _stmt(ReportStatementKind.FACT, f"Opportunity: {label}", value=label)
        for label in facts.best_opportunity_labels
    ]
    stmts.append(
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "Opportunities listed are HIGH score-band companies already stored in CompanyScore.",
        )
    )
    return stmts


def _section_problems(facts: ReportFacts) -> list[dict[str, Any]]:
    if not facts.problem_labels:
        return [
            _stmt(
                ReportStatementKind.FACT,
                "No explicit problem signals recorded (failures/blocks/pending approvals).",
                value="0",
            )
        ]
    return [
        _stmt(ReportStatementKind.FACT, label, value=label) for label in facts.problem_labels
    ]


def _section_worked(facts: ReportFacts) -> list[dict[str, Any]]:
    if not facts.worked_labels:
        return [_unavailable("What worked (no successful manager/decision signals in period)")]
    return [
        _stmt(ReportStatementKind.FACT, label, value=label) for label in facts.worked_labels
    ]


def _section_failed(facts: ReportFacts) -> list[dict[str, Any]]:
    if not facts.failed_labels:
        return [
            _stmt(
                ReportStatementKind.FACT,
                "No explicit failure signals recorded in manager decisions/runs for this period.",
                value="0",
            )
        ]
    return [
        _stmt(ReportStatementKind.FACT, label, value=label) for label in facts.failed_labels
    ]


def _section_strategy(facts: ReportFacts) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    if facts.companies_total > 0 and facts.qualified_leads == 0:
        recs.append(
            _stmt(
                ReportStatementKind.RECOMMENDATION,
                "Run scoring on researched companies — none currently have GOOD/HIGH bands.",
            )
        )
    if facts.qualified_leads > 0 and facts.audits_total == 0:
        recs.append(
            _stmt(
                ReportStatementKind.RECOMMENDATION,
                "Audit qualified companies to ground outreach in verified digital-presence evidence.",
            )
        )
    if facts.outreach_sent == 0 and facts.qualified_leads > 0:
        recs.append(
            _stmt(
                ReportStatementKind.RECOMMENDATION,
                "Draft and approve outreach for qualified leads (sending remains approval-gated).",
            )
        )
    if facts.pending_approvals > 0:
        recs.append(
            _stmt(
                ReportStatementKind.RECOMMENDATION,
                f"Clear {facts.pending_approvals} pending approval(s) before expanding outbound activity.",
            )
        )
    if facts.costs_available and facts.revenue_available and facts.gross_profit is not None:
        if facts.gross_profit < 0:
            recs.append(
                _stmt(
                    ReportStatementKind.RECOMMENDATION,
                    "Review cost categories with the highest spend; profit is negative on recorded ledger data.",
                )
            )
    if not recs:
        recs.append(
            _stmt(
                ReportStatementKind.RECOMMENDATION,
                "Continue collecting ledger and pipeline data — insufficient signals for a stronger strategic change.",
            )
        )
    recs.insert(
        0,
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "Strategy recommendations are rule-based from recorded facts only; they are not AI-generated forecasts.",
        ),
    )
    return recs


def _section_approvals(facts: ReportFacts) -> list[dict[str, Any]]:
    return [
        _stmt(
            ReportStatementKind.FACT,
            f"Pending approvals: {facts.pending_approvals}",
            value=str(facts.pending_approvals),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Pending YELLOW approvals: {facts.yellow_pending_approvals}",
            value=str(facts.yellow_pending_approvals),
        ),
        _stmt(
            ReportStatementKind.FACT,
            f"Pending RED approvals: {facts.red_pending_approvals}",
            value=str(facts.red_pending_approvals),
        ),
        _stmt(
            ReportStatementKind.RECOMMENDATION,
            (
                "Resolve pending approvals with an authorized human resolver."
                if facts.pending_approvals
                else "No approvals currently waiting."
            ),
        ),
    ]


def _section_priorities(facts: ReportFacts) -> list[dict[str, Any]]:
    priorities: list[str] = []
    if facts.pending_approvals:
        priorities.append("Resolve pending approvals")
    if facts.companies_total > facts.qualified_leads and facts.companies_total > 0:
        priorities.append("Score remaining unscored / low-band companies")
    if facts.qualified_leads > facts.audits_total:
        priorities.append("Audit qualified companies lacking audits")
    if facts.outreach_sent == 0 and facts.qualified_leads > 0:
        priorities.append("Prepare approved outreach for qualified leads")
    if facts.delivery_projects_active:
        priorities.append("Advance active delivery projects through verification")
    if facts.delivery_tasks_blocked:
        priorities.append("Unblock delivery tasks with unmet dependencies")
    if not priorities:
        priorities.append("Continue research/scoring loop to grow qualified pipeline")

    stmts = [
        _stmt(
            ReportStatementKind.INTERPRETATION,
            "Priorities are derived from current recorded gaps; they are recommendations, not commitments.",
        )
    ]
    for p in priorities:
        stmts.append(_stmt(ReportStatementKind.RECOMMENDATION, p, value=p))
    return stmts
