"""Deterministic outreach composer — only grounded personalization."""

from __future__ import annotations

from app.agents.sales.schemas import OutreachDraft, PersonalizationReason, SalesEvidenceItem
from app.models import Company, CompanyAudit, Lead

OUTREACH_VERSION = "1.0.0"


def compose_deterministic_draft(
    *,
    company: Company,
    lead: Lead,
    catalog: list[SalesEvidenceItem],
    audit: CompanyAudit | None,
) -> OutreachDraft:
    """Build a plain-spoken draft using only catalog facts.

    Avoids "I noticed" unless website availability is evidenced.
    Avoids website-specific claims unless audit.website_available is true.
    """
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

    website_ok = bool(audit and audit.website_available and "audit.website_available" in by_id)
    problem = _first_problem_text(audit) if website_ok else None
    opportunity = _first_opportunity_text(audit) if website_ok else None
    solution = (
        audit.recommended_solution.strip()
        if audit and audit.recommended_solution and "audit.recommended_solution" in by_id
        else None
    )

    body_parts: list[str] = [greeting, ""]

    if website_ok and company.website and "company.website" in by_id:
        use("company.website", "Reference the company's recorded public website URL.")
        use(
            "audit.website_available",
            "Website availability was verified in the audit record.",
        )
        if problem and "audit.problem.0" in by_id:
            use("audit.problem.0", "Reference a verified audit problem with evidence.")
            body_parts.append(
                f"I reviewed {company_name}'s public website ({company.website}) "
                f"and one clear gap stood out: {problem}."
            )
        else:
            body_parts.append(
                f"I reviewed {company_name}'s public website ({company.website}) "
                "and thought a short note might be useful."
            )
    else:
        industry = company.industry if "company.industry" in by_id else None
        if industry:
            use("company.industry", "Reference the company's recorded industry.")
            body_parts.append(
                f"I'm reaching out because {company_name} operates in {industry}, "
                "and I work with similar teams on quieter operational improvements."
            )
        else:
            body_parts.append(
                f"I'm reaching out about {company_name} — "
                "happy to keep this brief and specific to what would actually help."
            )

    if website_ok and opportunity and "audit.opportunity.0" in by_id:
        use("audit.opportunity.0", "Reference a verified audit opportunity.")
        body_parts.append(f"There also looks to be room to improve: {opportunity}.")

    if website_ok and solution:
        use(
            "audit.recommended_solution",
            "Reference the audit's recommended solution.",
        )
        body_parts.append(f"A practical next step could be: {solution}.")

    cta = "If useful, would you be open to a short call this week to compare notes?"
    body_parts.extend(["", cta, "", "Best regards"])

    subject = _subject(company_name=company_name, website_ok=website_ok, problem=problem)
    message = "\n".join(body_parts).strip()
    confidence = _confidence(
        website_ok=website_ok,
        has_problem=bool(problem),
        has_solution=bool(solution),
        has_name=bool(first_name),
    )

    seen: set[str] = set()
    evidence_used: list[str] = []
    for eid in used:
        if eid not in seen:
            seen.add(eid)
            evidence_used.append(eid)

    return OutreachDraft(
        subject=subject,
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


def _first_problem_text(audit: CompanyAudit | None) -> str | None:
    if not audit or not audit.problems:
        return None
    first = audit.problems[0]
    if not isinstance(first, dict):
        return None
    title = str(first.get("title") or "").strip()
    detail = str(first.get("detail") or "").strip()
    if title and detail:
        return f"{title} — {detail}"[:280]
    text = title or detail
    return text[:280] if text else None


def _first_opportunity_text(audit: CompanyAudit | None) -> str | None:
    if not audit or not audit.opportunities:
        return None
    first = audit.opportunities[0]
    if not isinstance(first, dict):
        return None
    title = str(first.get("title") or "").strip()
    detail = str(first.get("detail") or "").strip()
    if title and detail:
        return f"{title} — {detail}"[:280]
    text = title or detail
    return text[:280] if text else None


def _subject(*, company_name: str, website_ok: bool, problem: str | None) -> str:
    if website_ok and problem:
        return f"Quick thought on {company_name}'s website"
    return f"Quick note for {company_name}"


def _confidence(
    *,
    website_ok: bool,
    has_problem: bool,
    has_solution: bool,
    has_name: bool,
) -> float:
    score = 0.35
    if has_name:
        score += 0.1
    if website_ok:
        score += 0.2
    if has_problem:
        score += 0.2
    if has_solution:
        score += 0.15
    return round(min(score, 0.95), 3)
