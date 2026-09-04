"""Deterministic digital-presence observations from browser/search evidence.

Never invents signals — only maps observed page/search content.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.agents.audit.schemas import AuditEvidenceItem, SiteObservations
from app.providers.browser.types import BrowserPageSnapshot
from app.providers.search.types import SearchResult

AUDIT_VERSION = "1.0.0"

_CONTACT_RE = re.compile(r"\b(contact|kontakt|get\s+in\s+touch|reach\s+us)\b", re.I)
_BOOKING_RE = re.compile(
    r"\b(book|booking|schedule|appointment|termin|calendar|calendly)\b",
    re.I,
)
_FORM_RE = re.compile(r"\b(submit|send\s+message|contact\s+form|enquiry|inquiry|form)\b", re.I)
_CTA_RE = re.compile(
    r"\b(get\s+started|learn\s+more|request\s+demo|buy\s+now|sign\s+up|try\s+free|call\s+now)\b",
    re.I,
)
_EMAIL_RE = re.compile(r"mailto:", re.I)
_TEL_RE = re.compile(r"tel:", re.I)


def build_observations_from_browser(
    *,
    requested_url: str,
    snapshot: BrowserPageSnapshot | None,
    browser_error: str | None = None,
) -> tuple[SiteObservations, list[AuditEvidenceItem]]:
    evidence: list[AuditEvidenceItem] = []
    if snapshot is None:
        obs = SiteObservations(
            website_available=False,
            website_url=requested_url,
            browser_error=browser_error or "browser_unavailable",
            incomplete_site=True,
        )
        evidence.append(
            AuditEvidenceItem(
                evidence_id="E001",
                kind="browser_failure",
                url=requested_url,
                detail=obs.browser_error or "Website could not be fetched",
            )
        )
        return obs, evidence

    text = snapshot.visible_text or ""
    meta = snapshot.page_metadata or {}
    links = snapshot.links or []
    link_blob = " ".join(f"{link.url} {link.text}" for link in links)
    combined = f"{text}\n{link_blob}"

    has_viewport = any("viewport" in key.lower() for key in meta)
    has_mailto = bool(_EMAIL_RE.search(combined)) or any(
        (link.url or "").lower().startswith("mailto:") for link in links
    )
    has_tel = bool(_TEL_RE.search(combined)) or any(
        (link.url or "").lower().startswith("tel:") for link in links
    )
    has_contact = bool(_CONTACT_RE.search(combined))
    has_booking = bool(_BOOKING_RE.search(combined))
    has_form = bool(_FORM_RE.search(combined))
    has_cta = bool(_CTA_RE.search(combined))
    incomplete = len(text.strip()) < 80 and len(links) < 3

    obs = SiteObservations(
        website_available=True,
        website_url=requested_url,
        final_url=snapshot.final_url,
        status_code=snapshot.status_code,
        title=snapshot.title or None,
        text_length=len(text),
        has_viewport_meta=has_viewport,
        has_mailto=has_mailto,
        has_tel=has_tel,
        has_contact_link=has_contact,
        has_booking_link=has_booking,
        has_form_signal=has_form,
        has_cta_signal=has_cta,
        link_count=len(links),
        incomplete_site=incomplete,
        browser_error=None,
    )

    evidence.append(
        AuditEvidenceItem(
            evidence_id="E001",
            kind="page_fetch",
            url=snapshot.final_url,
            excerpt=(snapshot.title or "")[:200] or None,
            detail=f"Fetched page status={snapshot.status_code} text_chars={len(text)} links={len(links)}",
        )
    )
    if has_viewport:
        evidence.append(
            AuditEvidenceItem(
                evidence_id="E002",
                kind="mobile_viewport",
                url=snapshot.final_url,
                detail="Viewport meta tag present in page metadata",
            )
        )
    else:
        evidence.append(
            AuditEvidenceItem(
                evidence_id="E002",
                kind="mobile_viewport_missing",
                url=snapshot.final_url,
                detail="No viewport meta tag observed in page metadata",
            )
        )

    eid = 3
    for flag, kind, detail in (
        (has_mailto, "mailto", "mailto: link/text observed"),
        (has_tel, "tel", "tel: link/text observed"),
        (has_contact, "contact", "Contact-related link/text observed"),
        (has_booking, "booking", "Booking/appointment-related link/text observed"),
        (has_form, "form", "Form/inquiry-related wording observed"),
        (has_cta, "cta", "CTA wording observed"),
    ):
        if flag:
            evidence.append(
                AuditEvidenceItem(
                    evidence_id=f"E{eid:03d}",
                    kind=kind,
                    url=snapshot.final_url,
                    detail=detail,
                )
            )
            eid += 1

    if incomplete:
        evidence.append(
            AuditEvidenceItem(
                evidence_id=f"E{eid:03d}",
                kind="incomplete_site",
                url=snapshot.final_url,
                detail=f"Sparse page content (text_chars={len(text)}, links={len(links)})",
            )
        )

    return obs, evidence


def append_search_evidence(
    observations: SiteObservations,
    evidence: list[AuditEvidenceItem],
    results: list[SearchResult],
    *,
    search_error: str | None = None,
) -> tuple[SiteObservations, list[AuditEvidenceItem]]:
    next_id = len(evidence) + 1
    if search_error:
        evidence = [
            *evidence,
            AuditEvidenceItem(
                evidence_id=f"E{next_id:03d}",
                kind="search_failure",
                detail=search_error,
            ),
        ]
        return (
            observations.model_copy(update={"search_error": search_error, "search_result_count": 0}),
            evidence,
        )

    new_items: list[AuditEvidenceItem] = []
    for index, result in enumerate(results):
        new_items.append(
            AuditEvidenceItem(
                evidence_id=f"E{next_id + index:03d}",
                kind="search_result",
                url=result.url,
                excerpt=(result.snippet or result.title or "")[:300] or None,
                detail=f"Search hit title={result.title!r} domain={result.domain}",
            )
        )
    updated = observations.model_copy(update={"search_result_count": len(results)})
    return updated, [*evidence, *new_items]


def deterministic_findings(
    observations: SiteObservations,
    evidence: list[AuditEvidenceItem],
) -> tuple[list, list, str, str]:
    """Return (problems, opportunities, summary, recommended_solution) from observations only."""
    from app.agents.audit.schemas import AuditFinding

    by_id = {item.evidence_id: item for item in evidence}
    problems: list[AuditFinding] = []
    opportunities: list[AuditFinding] = []

    def _cite(*kinds: str) -> list[str]:
        ids = [item.evidence_id for item in evidence if item.kind in kinds]
        return ids or (["E001"] if "E001" in by_id else [evidence[0].evidence_id])

    if not observations.website_available:
        problems.append(
            AuditFinding(
                finding_type="problem",
                title="Website unavailable",
                detail="The company website could not be fetched for public audit.",
                priority="critical",
                evidence_ids=_cite("browser_failure", "page_fetch"),
                confidence=0.95,
                recommended_solution="Restore website availability and confirm public DNS/hosting.",
            )
        )
    else:
        if not observations.has_viewport_meta:
            problems.append(
                AuditFinding(
                    finding_type="problem",
                    title="Weak mobile usability signal",
                    detail="No viewport meta tag was observed — mobile rendering may be poor.",
                    priority="medium",
                    evidence_ids=_cite("mobile_viewport_missing"),
                    confidence=0.8,
                    recommended_solution="Add a responsive viewport meta tag and verify mobile layout.",
                )
            )
        if not observations.has_contact_link and not observations.has_mailto and not observations.has_tel:
            problems.append(
                AuditFinding(
                    finding_type="problem",
                    title="Limited public contact methods",
                    detail="No clear contact link, mailto, or tel signal was observed.",
                    priority="high",
                    evidence_ids=_cite("page_fetch"),
                    confidence=0.75,
                    recommended_solution="Add visible contact channels (page, email, and/or phone).",
                )
            )
            opportunities.append(
                AuditFinding(
                    finding_type="opportunity",
                    title="Missed inbound leads from weak contact capture",
                    detail="Visitors may leave without a clear way to inquire.",
                    priority="high",
                    evidence_ids=_cite("page_fetch"),
                    confidence=0.7,
                    recommended_solution="Add a prominent contact CTA and simple inquiry form.",
                    estimated_business_value=None,
                )
            )
        if not observations.has_form_signal:
            opportunities.append(
                AuditFinding(
                    finding_type="opportunity",
                    title="Lead capture form not observed",
                    detail="No form/inquiry wording was detected on the fetched page.",
                    priority="medium",
                    evidence_ids=_cite("page_fetch", "form"),
                    confidence=0.65,
                    recommended_solution="Add a short inquiry form above the fold.",
                )
            )
        if not observations.has_booking_link:
            opportunities.append(
                AuditFinding(
                    finding_type="opportunity",
                    title="No booking/appointment flow observed",
                    detail="No booking/calendar signals were detected.",
                    priority="medium",
                    evidence_ids=_cite("page_fetch", "booking"),
                    confidence=0.6,
                    recommended_solution="Add online booking or appointment scheduling if services are appointment-based.",
                )
            )
        if not observations.has_cta_signal:
            opportunities.append(
                AuditFinding(
                    finding_type="opportunity",
                    title="Weak CTA presence",
                    detail="Common call-to-action phrases were not observed.",
                    priority="low",
                    evidence_ids=_cite("page_fetch", "cta"),
                    confidence=0.55,
                    recommended_solution="Add clear primary CTAs for inquiry or conversion.",
                )
            )
        if observations.incomplete_site:
            problems.append(
                AuditFinding(
                    finding_type="problem",
                    title="Incomplete or sparse website content",
                    detail="Fetched page has very little visible text and few links.",
                    priority="high",
                    evidence_ids=_cite("incomplete_site", "page_fetch"),
                    confidence=0.85,
                    recommended_solution="Expand core pages (services, about, contact) with clear offers.",
                )
            )
        if observations.search_result_count == 0 and not observations.search_error:
            opportunities.append(
                AuditFinding(
                    finding_type="opportunity",
                    title="Thin online presence in search sample",
                    detail="No additional search hits were collected for this company in the audit sample.",
                    priority="low",
                    evidence_ids=_cite("page_fetch"),
                    confidence=0.5,
                    recommended_solution="Improve public listings and content discoverability.",
                )
            )

    if not observations.website_available:
        summary = "Website unavailable — public digital presence could not be audited beyond fetch failure."
        solution = "Restore website availability, then re-run audit."
        return problems, opportunities, summary, solution

    summary_parts = [
        f"Audited {observations.final_url or observations.website_url}.",
        f"Contact signals: mailto={observations.has_mailto}, tel={observations.has_tel}, contact={observations.has_contact_link}.",
        f"Capture signals: form={observations.has_form_signal}, booking={observations.has_booking_link}, cta={observations.has_cta_signal}.",
        f"Mobile viewport meta observed={observations.has_viewport_meta}.",
    ]
    summary = " ".join(summary_parts)
    solution = (
        "Prioritize contact/lead-capture clarity, mobile basics, and conversion CTAs "
        "based on observed gaps."
    )
    return problems, opportunities, summary, solution


def pick_priority(problems: list, opportunities: list) -> str:
    order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    best = 0
    label = "low"
    for item in [*problems, *opportunities]:
        value = order.get(getattr(item, "priority", "low"), 0)
        if value > best:
            best = value
            label = item.priority
    if not problems and not opportunities:
        return "low"
    return label


def evidence_urls(evidence: list[AuditEvidenceItem]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        if not item.url:
            continue
        try:
            parts = urlsplit(item.url)
        except ValueError:
            continue
        if parts.scheme not in {"http", "https"}:
            continue
        if item.url in seen:
            continue
        seen.add(item.url)
        urls.append(item.url)
    return urls
