"""Validate outreach drafts — block fabrication, spam, and ungrounded claims."""

from __future__ import annotations

import re

from app.agents.sales.schemas import OutreachDraft, PersonalizationReason, SalesAIEnrichment, SalesEvidenceItem
from app.exceptions import ValidationAppError

# Observation claims that require verified website evidence in the catalog.
_NOTICED_RE = re.compile(
    r"\b(i noticed|i've noticed|i saw that|i came across|your website has)\b",
    re.IGNORECASE,
)

_SPAM_RE = re.compile(
    r"\b("
    r"guaranteed|game[- ]?changer|revolutionary|limited time|act now|urgent|"
    r"once in a lifetime|100%|risk[- ]?free|make money fast|inbox exploding|"
    r"crushing it|synergy|leverage our cutting[- ]?edge"
    r")\b",
    re.IGNORECASE,
)

_FAKE_CUSTOMER_RE = re.compile(
    r"\b(our (?:client|customer)s? (?:love|saw|increased|grew)|"
    r"as featured in|forbes|nytimes|"
    r"\d{2,}% (?:increase|growth|boost))\b",
    re.IGNORECASE,
)


def validate_reasons(
    reasons: list[PersonalizationReason],
    catalog: list[SalesEvidenceItem],
) -> list[PersonalizationReason]:
    allowed = {item.evidence_id for item in catalog}
    valid: list[PersonalizationReason] = []
    for reason in reasons:
        if not reason.evidence_ids:
            continue
        if any(eid not in allowed for eid in reason.evidence_ids):
            continue
        valid.append(reason)
    return valid


def validate_outreach_draft(
    draft: OutreachDraft,
    catalog: list[SalesEvidenceItem],
    *,
    website_verified: bool,
) -> OutreachDraft:
    """Reject or sanitize drafts that fabricate personalization."""
    if not draft.subject.strip() or not draft.message.strip() or not draft.cta.strip():
        raise ValidationAppError("Outreach draft missing subject, message, or CTA")

    reasons = validate_reasons(draft.personalization_reasons, catalog)
    if not reasons:
        raise ValidationAppError(
            "Outreach draft has no valid evidence-backed personalization reasons"
        )

    text = f"{draft.subject}\n{draft.message}\n{draft.cta}"
    if _SPAM_RE.search(text):
        raise ValidationAppError(
            "Outreach draft contains spam or exaggerated language",
            details={"pattern": "spam"},
        )
    if _FAKE_CUSTOMER_RE.search(text):
        raise ValidationAppError(
            "Outreach draft contains unverifiable customer claims",
            details={"pattern": "fake_customer"},
        )

    # "I noticed" / "Your website has" only allowed when website was verified
    if _NOTICED_RE.search(text) and not website_verified:
        raise ValidationAppError(
            "Outreach claims observation/website details without verified website evidence",
            details={"pattern": "ungrounded_observation"},
        )

    allowed = {item.evidence_id for item in catalog}
    evidence_used = [eid for eid in draft.evidence_used if eid in allowed]
    # Ensure every used id also appears in reasons
    reason_ids = {eid for r in reasons for eid in r.evidence_ids}
    evidence_used = [eid for eid in evidence_used if eid in reason_ids] or sorted(reason_ids)

    return draft.model_copy(
        update={
            "personalization_reasons": reasons,
            "evidence_used": evidence_used,
        }
    )


def validate_ai_enrichment(
    enrichment: SalesAIEnrichment,
    catalog: list[SalesEvidenceItem],
    *,
    website_verified: bool,
) -> OutreachDraft:
    """Convert AI enrichment into a validated OutreachDraft or raise."""
    draft = OutreachDraft(
        subject=enrichment.subject,
        message=enrichment.message,
        cta=enrichment.cta,
        personalization_reasons=enrichment.personalization_reasons
        or [
            # Fallback will fail validation if empty — intentional
        ],
        evidence_used=[
            eid for r in enrichment.personalization_reasons for eid in r.evidence_ids
        ],
        confidence=enrichment.confidence,
    )
    return validate_outreach_draft(draft, catalog, website_verified=website_verified)
