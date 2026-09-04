"""Opportunity / lead lifecycle derivation and legal transitions."""

from __future__ import annotations

import enum
from typing import Any


class OpportunityLifecycle(str, enum.Enum):
    DISCOVERED = "discovered"
    VERIFIED = "verified"
    SCORED = "scored"
    AUDITED = "audited"
    QUALIFIED = "qualified"
    OUTREACH_DRAFTED = "outreach_drafted"
    PENDING_APPROVAL = "pending_approval"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CUSTOMER = "customer"
    LOST = "lost"
    DISQUALIFIED = "disqualified"
    BLOCKED = "blocked"


# Soft progression (not every path is forced)
LIFECYCLE_TRANSITIONS: dict[OpportunityLifecycle, frozenset[OpportunityLifecycle]] = {
    OpportunityLifecycle.DISCOVERED: frozenset(
        {
            OpportunityLifecycle.VERIFIED,
            OpportunityLifecycle.SCORED,
            OpportunityLifecycle.DISQUALIFIED,
            OpportunityLifecycle.BLOCKED,
            OpportunityLifecycle.LOST,
        }
    ),
    OpportunityLifecycle.VERIFIED: frozenset(
        {
            OpportunityLifecycle.SCORED,
            OpportunityLifecycle.DISQUALIFIED,
            OpportunityLifecycle.BLOCKED,
            OpportunityLifecycle.LOST,
        }
    ),
    OpportunityLifecycle.SCORED: frozenset(
        {
            OpportunityLifecycle.AUDITED,
            OpportunityLifecycle.QUALIFIED,
            OpportunityLifecycle.DISQUALIFIED,
            OpportunityLifecycle.BLOCKED,
            OpportunityLifecycle.LOST,
        }
    ),
    OpportunityLifecycle.AUDITED: frozenset(
        {
            OpportunityLifecycle.QUALIFIED,
            OpportunityLifecycle.OUTREACH_DRAFTED,
            OpportunityLifecycle.DISQUALIFIED,
            OpportunityLifecycle.BLOCKED,
            OpportunityLifecycle.LOST,
        }
    ),
    OpportunityLifecycle.QUALIFIED: frozenset(
        {
            OpportunityLifecycle.OUTREACH_DRAFTED,
            OpportunityLifecycle.PENDING_APPROVAL,
            OpportunityLifecycle.CONTACTED,
            OpportunityLifecycle.DISQUALIFIED,
            OpportunityLifecycle.BLOCKED,
            OpportunityLifecycle.LOST,
        }
    ),
    OpportunityLifecycle.OUTREACH_DRAFTED: frozenset(
        {
            OpportunityLifecycle.PENDING_APPROVAL,
            OpportunityLifecycle.CONTACTED,
            OpportunityLifecycle.LOST,
            OpportunityLifecycle.DISQUALIFIED,
        }
    ),
    OpportunityLifecycle.PENDING_APPROVAL: frozenset(
        {
            OpportunityLifecycle.CONTACTED,
            OpportunityLifecycle.OUTREACH_DRAFTED,
            OpportunityLifecycle.LOST,
            OpportunityLifecycle.QUALIFIED,
        }
    ),
    OpportunityLifecycle.CONTACTED: frozenset(
        {
            OpportunityLifecycle.RESPONDED,
            OpportunityLifecycle.CUSTOMER,
            OpportunityLifecycle.LOST,
            OpportunityLifecycle.BLOCKED,
        }
    ),
    OpportunityLifecycle.RESPONDED: frozenset(
        {
            OpportunityLifecycle.CUSTOMER,
            OpportunityLifecycle.LOST,
            OpportunityLifecycle.BLOCKED,
        }
    ),
    OpportunityLifecycle.CUSTOMER: frozenset({OpportunityLifecycle.LOST}),
    OpportunityLifecycle.LOST: frozenset(),
    OpportunityLifecycle.DISQUALIFIED: frozenset(),
    OpportunityLifecycle.BLOCKED: frozenset(
        {
            OpportunityLifecycle.QUALIFIED,
            OpportunityLifecycle.DISCOVERED,
            OpportunityLifecycle.LOST,
        }
    ),
}


def can_lifecycle_transition(
    current: OpportunityLifecycle | str, nxt: OpportunityLifecycle | str
) -> bool:
    cur = (
        current
        if isinstance(current, OpportunityLifecycle)
        else OpportunityLifecycle(current)
    )
    nxt_s = nxt if isinstance(nxt, OpportunityLifecycle) else OpportunityLifecycle(nxt)
    if cur == nxt_s:
        return True
    return nxt_s in LIFECYCLE_TRANSITIONS.get(cur, frozenset())


def derive_lifecycle_state(
    *,
    company: Any,
    score: Any | None,
    audit: Any | None,
    outreach: Any | None,
    lead: Any | None,
    is_customer: bool,
) -> str:
    """Derive owner-facing lifecycle from persisted facts — never invent."""
    if is_customer:
        return OpportunityLifecycle.CUSTOMER.value

    lead_status = None
    if lead is not None:
        lead_status = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
        if getattr(lead, "blocked", False):
            return OpportunityLifecycle.BLOCKED.value
        if lead_status == "disqualified":
            return OpportunityLifecycle.DISQUALIFIED.value
        if lead_status == "converted":
            return OpportunityLifecycle.CUSTOMER.value

    if outreach is not None:
        st = outreach.status.value if hasattr(outreach.status, "value") else str(outreach.status)
        if st in {"sent", "delivered"}:
            return OpportunityLifecycle.CONTACTED.value
        if st in {"pending_approval"}:
            return OpportunityLifecycle.PENDING_APPROVAL.value
        if st in {"draft", "drafted"}:
            return OpportunityLifecycle.OUTREACH_DRAFTED.value
        if st in {"rejected", "cancelled"}:
            return OpportunityLifecycle.LOST.value

    if lead_status == "contacted":
        return OpportunityLifecycle.CONTACTED.value
    if lead_status == "qualified":
        return OpportunityLifecycle.QUALIFIED.value

    if audit is not None:
        return OpportunityLifecycle.AUDITED.value
    if score is not None:
        return OpportunityLifecycle.SCORED.value

    website = getattr(company, "website", None) or getattr(company, "website_domain", None)
    sources = getattr(company, "sources", None)
    if website or (sources and len(sources) > 0):
        return OpportunityLifecycle.VERIFIED.value
    return OpportunityLifecycle.DISCOVERED.value
