"""Personalized follow-up draft composer — calm, evidence-grounded, non-spammy."""

from __future__ import annotations

from app.agents.sales.schemas import OutreachDraft, PersonalizationReason, SalesEvidenceItem
from app.models import Company, Lead, Outreach

FOLLOWUP_VERSION = "1.0.0"


def compose_followup_draft(
    *,
    company: Company,
    lead: Lead,
    catalog: list[SalesEvidenceItem],
    initial_outreach: Outreach,
    followup_index: int,
) -> OutreachDraft:
    """Compose a short personalized follow-up referencing the prior outreach only."""
    by_id = {item.evidence_id: item for item in catalog}
    reasons: list[PersonalizationReason] = []
    used: list[str] = []

    def use(eid: str, reason: str) -> None:
        if eid not in by_id:
            return
        used.append(eid)
        reasons.append(PersonalizationReason(reason=reason, evidence_ids=[eid]))

    first_name = _first_name(lead.name) if "lead.name" in by_id else None
    company_name = company.name
    use("company.name", f"Address the company by its recorded name ({company_name}).")
    if first_name:
        use("lead.name", f"Greet the lead using their recorded name ({lead.name}).")

    greeting = f"Hi {first_name}," if first_name else "Hello,"
    prior_subject = (initial_outreach.subject or "").strip()

    if followup_index == 1:
        subject = f"Re: {prior_subject}" if prior_subject else f"Following up — {company_name}"
        body_parts = [
            greeting,
            "",
            (
                f"Just floating this back up in case my earlier note about {company_name} "
                "got buried."
            ),
        ]
        if prior_subject:
            body_parts.append(f"I had written about: {prior_subject}.")
        use(
            "company.name",
            "Reference the prior outreach subject without inventing new claims.",
        )
        cta = "If timing is better now, would a brief call still be useful?"
    else:
        subject = (
            f"Last note on {company_name}"
            if company_name
            else "Last note — happy to close the loop"
        )
        body_parts = [
            greeting,
            "",
            (
                f"I'll keep this short — I don't want to crowd your inbox. "
                f"If {company_name} isn't the right fit right now, no need to reply."
            ),
        ]
        cta = "If it is useful later, I'm happy to reconnect when the timing is better."
        use(
            "company.name",
            "Second follow-up closes politely without urgency or pressure.",
        )

    body_parts.extend(["", cta, "", "Best regards"])
    message = "\n".join(body_parts).strip()

    confidence = 0.45
    if first_name:
        confidence += 0.1
    if prior_subject:
        confidence += 0.15
    if followup_index == 1:
        confidence += 0.1
    confidence = round(min(confidence, 0.9), 3)

    seen: set[str] = set()
    evidence_used: list[str] = []
    for eid in used:
        if eid not in seen:
            seen.add(eid)
            evidence_used.append(eid)

    return OutreachDraft(
        subject=subject[:300],
        message=message,
        cta=cta,
        personalization_reasons=reasons,
        evidence_used=evidence_used,
        confidence=confidence,
    )


def _first_name(full_name: str) -> str | None:
    parts = full_name.strip().split()
    if not parts:
        return None
    return parts[0]
