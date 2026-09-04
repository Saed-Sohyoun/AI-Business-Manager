"""Deterministic lead scoring engine (v1).

Rules are explicit and versioned. An LLM must never assign the final score.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.scoring.bands import band_for_total, band_literal
from app.scoring.schemas import (
    CategoryScore,
    CompanyScoringFacts,
    LeadScoreResult,
    ScoreReason,
)

SCORING_VERSION = "1.0.0"
CATEGORY_MAX = 20

# Observed commercial keywords — only applied against provided description text.
_COMMERCIAL_KEYWORDS = (
    "b2b",
    "saas",
    "software",
    "agency",
    "consulting",
    "service",
    "services",
    "shop",
    "store",
    "studio",
    "gmbh",
    "ltd",
    "llc",
    "inc",
)

# Industries that often benefit from ops automation (heuristic, deterministic).
_AUTOMATION_INDUSTRIES = (
    "agency",
    "marketing",
    "consulting",
    "services",
    "cleaning",
    "plumbing",
    "hvac",
    "legal",
    "accounting",
    "clinic",
    "dental",
    "salon",
    "restaurant",
    "real estate",
    "construction",
)


def score_company_facts(
    facts: CompanyScoringFacts,
    *,
    scored_at: datetime | None = None,
) -> LeadScoreResult:
    """Score validated facts. Same facts always yield the same result."""
    when = scored_at or datetime.now(timezone.utc)

    wq_score, wq_reasons = _score_website_quality(facts)
    op_score, op_reasons = _score_online_presence(facts)
    lc_score, lc_reasons = _score_lead_capture(facts)
    ap_score, ap_reasons = _score_automation_potential(facts)
    cp_score, cp_reasons = _score_commercial_potential(facts)

    total = wq_score + op_score + lc_score + ap_score + cp_score
    if total < 0 or total > 100:
        raise RuntimeError(f"invariant violated: total_score={total}")

    band = band_for_total(total)
    reasons = wq_reasons + op_reasons + lc_reasons + ap_reasons + cp_reasons
    evidence = facts.model_dump()

    categories = [
        CategoryScore(name="website_quality", score=wq_score, reasons=wq_reasons),
        CategoryScore(name="online_presence", score=op_score, reasons=op_reasons),
        CategoryScore(name="lead_capture_process", score=lc_score, reasons=lc_reasons),
        CategoryScore(name="automation_potential", score=ap_score, reasons=ap_reasons),
        CategoryScore(name="commercial_potential", score=cp_score, reasons=cp_reasons),
    ]

    return LeadScoreResult(
        total_score=total,
        band=band_literal(band),
        website_quality=wq_score,
        online_presence=op_score,
        lead_capture_process=lc_score,
        automation_potential=ap_score,
        commercial_potential=cp_score,
        reasons=reasons,
        evidence=evidence,
        scoring_version=SCORING_VERSION,
        scored_at=when,
        categories=categories,
    )


def _clamp(points: int) -> int:
    return max(0, min(CATEGORY_MAX, points))


def _score_website_quality(facts: CompanyScoringFacts) -> tuple[int, list[ScoreReason]]:
    points = 0
    reasons: list[ScoreReason] = []

    if facts.has_website:
        points += 5
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=5,
                reason="Company has a website URL on record",
                evidence_keys=["has_website"],
            )
        )
    if facts.website_verified:
        points += 5
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=5,
                reason="Website was verified (reachable on own domain)",
                evidence_keys=["website_verified"],
            )
        )
    if facts.website_https:
        points += 3
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=3,
                reason="Website uses HTTPS",
                evidence_keys=["website_https"],
            )
        )
    if facts.has_description:
        points += 3
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=3,
                reason="Description evidence is present",
                evidence_keys=["has_description"],
            )
        )
    if facts.description_length >= 80:
        points += 4
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=4,
                reason="Description length indicates substantive public content (>=80 chars)",
                evidence_keys=["description_length"],
            )
        )
    elif facts.description_length >= 20:
        points += 2
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=2,
                reason="Description length is partial (20–79 chars)",
                evidence_keys=["description_length"],
            )
        )

    if points == 0:
        reasons.append(
            ScoreReason(
                category="website_quality",
                points=0,
                reason="No website quality signals available",
                evidence_keys=["has_website", "has_description"],
            )
        )
    return _clamp(points), reasons


def _score_online_presence(facts: CompanyScoringFacts) -> tuple[int, list[ScoreReason]]:
    points = 0
    reasons: list[ScoreReason] = []

    if facts.source_count >= 4:
        pts = 12
    elif facts.source_count >= 2:
        pts = 8
    elif facts.source_count == 1:
        pts = 4
    else:
        pts = 0
    if pts:
        points += pts
        reasons.append(
            ScoreReason(
                category="online_presence",
                points=pts,
                reason=f"Public source URL count = {facts.source_count}",
                evidence_keys=["source_count"],
            )
        )

    if facts.has_industry:
        points += 4
        reasons.append(
            ScoreReason(
                category="online_presence",
                points=4,
                reason="Industry is known from research evidence",
                evidence_keys=["has_industry", "industry"],
            )
        )
    if facts.has_location:
        points += 4
        reasons.append(
            ScoreReason(
                category="online_presence",
                points=4,
                reason="Location is known from research evidence",
                evidence_keys=["has_location"],
            )
        )

    if points == 0:
        reasons.append(
            ScoreReason(
                category="online_presence",
                points=0,
                reason="No online presence signals available",
                evidence_keys=["source_count", "has_industry", "has_location"],
            )
        )
    return _clamp(points), reasons


def _score_lead_capture(facts: CompanyScoringFacts) -> tuple[int, list[ScoreReason]]:
    points = 0
    reasons: list[ScoreReason] = []

    if facts.has_contact_form:
        points += 8
        reasons.append(
            ScoreReason(
                category="lead_capture_process",
                points=8,
                reason="Contact form signal present",
                evidence_keys=["has_contact_form"],
            )
        )
    if facts.has_contact_page:
        points += 4
        reasons.append(
            ScoreReason(
                category="lead_capture_process",
                points=4,
                reason="Contact page signal present",
                evidence_keys=["has_contact_page"],
            )
        )
    if facts.has_booking_or_calendar:
        points += 4
        reasons.append(
            ScoreReason(
                category="lead_capture_process",
                points=4,
                reason="Booking/calendar signal present",
                evidence_keys=["has_booking_or_calendar"],
            )
        )
    if facts.has_email_evidence:
        points += 2
        reasons.append(
            ScoreReason(
                category="lead_capture_process",
                points=2,
                reason="Email evidence recorded (not invented)",
                evidence_keys=["has_email_evidence"],
            )
        )
    if facts.has_phone_evidence:
        points += 2
        reasons.append(
            ScoreReason(
                category="lead_capture_process",
                points=2,
                reason="Phone evidence recorded (not invented)",
                evidence_keys=["has_phone_evidence"],
            )
        )

    if points == 0:
        reasons.append(
            ScoreReason(
                category="lead_capture_process",
                points=0,
                reason="No lead-capture signals observed",
                evidence_keys=[
                    "has_contact_form",
                    "has_contact_page",
                    "has_booking_or_calendar",
                    "has_email_evidence",
                    "has_phone_evidence",
                ],
            )
        )
    return _clamp(points), reasons


def _score_automation_potential(facts: CompanyScoringFacts) -> tuple[int, list[ScoreReason]]:
    """Automation readiness from observed digital/ops signals (deterministic)."""
    points = 0
    reasons: list[ScoreReason] = []

    if facts.has_website:
        points += 5
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=5,
                reason="Website present — digital channel available for automation",
                evidence_keys=["has_website"],
            )
        )
    if facts.has_industry:
        points += 4
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=4,
                reason="Industry known — playbooks can be specialized",
                evidence_keys=["has_industry", "industry"],
            )
        )
    if facts.has_location:
        points += 3
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=3,
                reason="Location known — local/ops automation can be scoped",
                evidence_keys=["has_location"],
            )
        )
    if facts.description_length >= 40:
        points += 4
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=4,
                reason="Enough public description text to support automated analysis",
                evidence_keys=["description_length"],
            )
        )
    if facts.source_count >= 2:
        points += 4
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=4,
                reason="Multiple public sources enable richer automated enrichment",
                evidence_keys=["source_count"],
            )
        )
    elif facts.has_website and not facts.has_contact_form and not facts.has_booking_or_calendar:
        # Opportunity bonus only when readiness signals incomplete (does not block max path)
        points += 2
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=2,
                reason="Website without form/booking — intake automation opportunity",
                evidence_keys=["has_website", "has_contact_form", "has_booking_or_calendar"],
            )
        )

    industry = (facts.industry or "").lower()
    if industry and any(token in industry for token in _AUTOMATION_INDUSTRIES):
        # Cap still enforced by _clamp; may overlap with has_industry points
        extra = min(2, CATEGORY_MAX - points) if points < CATEGORY_MAX else 0
        if extra:
            points += extra
            reasons.append(
                ScoreReason(
                    category="automation_potential",
                    points=extra,
                    reason="Industry profile commonly benefits from process automation",
                    evidence_keys=["industry"],
                )
            )

    if points == 0:
        reasons.append(
            ScoreReason(
                category="automation_potential",
                points=0,
                reason="No automation-readiness signals matched",
                evidence_keys=["has_website", "has_industry", "has_location"],
            )
        )
    return _clamp(points), reasons


def _score_commercial_potential(facts: CompanyScoringFacts) -> tuple[int, list[ScoreReason]]:
    points = 0
    reasons: list[ScoreReason] = []

    if facts.has_location:
        points += 5
        reasons.append(
            ScoreReason(
                category="commercial_potential",
                points=5,
                reason="Location known — geographically addressable",
                evidence_keys=["has_location"],
            )
        )
    if facts.has_industry:
        points += 5
        reasons.append(
            ScoreReason(
                category="commercial_potential",
                points=5,
                reason="Industry known — segmentable commercially",
                evidence_keys=["has_industry", "industry"],
            )
        )
    if facts.website_verified:
        points += 5
        reasons.append(
            ScoreReason(
                category="commercial_potential",
                points=5,
                reason="Verified website increases commercial credibility",
                evidence_keys=["website_verified"],
            )
        )

    desc = (facts.description or "").lower()
    if desc and any(keyword in desc for keyword in _COMMERCIAL_KEYWORDS):
        points += 5
        reasons.append(
            ScoreReason(
                category="commercial_potential",
                points=5,
                reason="Description contains commercial/business keywords (observed text only)",
                evidence_keys=["description"],
            )
        )
    elif facts.has_address_evidence:
        points += 3
        reasons.append(
            ScoreReason(
                category="commercial_potential",
                points=3,
                reason="Address evidence present",
                evidence_keys=["has_address_evidence"],
            )
        )

    if points == 0:
        reasons.append(
            ScoreReason(
                category="commercial_potential",
                points=0,
                reason="No commercial potential signals available",
                evidence_keys=["has_location", "has_industry", "website_verified", "description"],
            )
        )
    return _clamp(points), reasons
