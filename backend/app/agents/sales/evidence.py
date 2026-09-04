"""Build an evidence catalog from company memory — never invent facts."""

from __future__ import annotations

from typing import Any

from app.agents.sales.schemas import SalesEvidenceItem
from app.models import Company, CompanyAudit, CompanyScore, Lead


def _add(
    catalog: list[SalesEvidenceItem],
    *,
    evidence_id: str,
    kind: str,
    detail: str,
    source: str,
    url: str | None = None,
) -> None:
    catalog.append(
        SalesEvidenceItem(
            evidence_id=evidence_id,
            kind=kind,
            detail=detail[:1000],
            source=source,
            url=url,
        )
    )


def build_sales_evidence_catalog(
    *,
    company: Company,
    lead: Lead,
    score: CompanyScore | None,
    audit: CompanyAudit | None,
) -> list[SalesEvidenceItem]:
    catalog: list[SalesEvidenceItem] = []

    _add(
        catalog,
        evidence_id="company.name",
        kind="company_name",
        detail=company.name,
        source="company",
    )
    if company.website:
        _add(
            catalog,
            evidence_id="company.website",
            kind="website_url",
            detail=company.website,
            source="company",
            url=company.website,
        )
    if company.website_domain:
        _add(
            catalog,
            evidence_id="company.website_domain",
            kind="website_domain",
            detail=company.website_domain,
            source="company",
        )
    if company.industry:
        _add(
            catalog,
            evidence_id="company.industry",
            kind="industry",
            detail=company.industry,
            source="company",
        )
    if company.location:
        _add(
            catalog,
            evidence_id="company.location",
            kind="location",
            detail=company.location,
            source="company",
        )

    if lead.name:
        _add(
            catalog,
            evidence_id="lead.name",
            kind="lead_name",
            detail=lead.name,
            source="lead",
        )
    if lead.job_title:
        _add(
            catalog,
            evidence_id="lead.job_title",
            kind="job_title",
            detail=lead.job_title,
            source="lead",
        )
    if lead.email:
        _add(
            catalog,
            evidence_id="lead.email",
            kind="email",
            detail=lead.email,
            source="lead",
        )

    if score is not None:
        _add(
            catalog,
            evidence_id="score.total",
            kind="lead_score",
            detail=f"total_score={score.total_score} band={score.band}",
            source="company_score",
        )
        for idx, reason in enumerate(score.reasons or []):
            if not isinstance(reason, dict):
                continue
            text = str(reason.get("reason") or reason.get("detail") or "").strip()
            if not text:
                continue
            _add(
                catalog,
                evidence_id=f"score.reason.{idx}",
                kind="score_reason",
                detail=text,
                source="company_score",
            )

    if audit is not None:
        _add(
            catalog,
            evidence_id="audit.website_available",
            kind="website_availability",
            detail=f"website_available={bool(audit.website_available)}",
            source="company_audit",
            url=company.website if audit.website_available else None,
        )
        if audit.summary:
            _add(
                catalog,
                evidence_id="audit.summary",
                kind="audit_summary",
                detail=audit.summary,
                source="company_audit",
            )
        if audit.recommended_solution:
            _add(
                catalog,
                evidence_id="audit.recommended_solution",
                kind="recommended_solution",
                detail=audit.recommended_solution,
                source="company_audit",
            )
        for idx, problem in enumerate(audit.problems or []):
            if not isinstance(problem, dict):
                continue
            title = str(problem.get("title") or problem.get("detail") or "").strip()
            if not title:
                continue
            detail = title
            if problem.get("detail"):
                detail = f"{title}: {problem.get('detail')}"
            _add(
                catalog,
                evidence_id=f"audit.problem.{idx}",
                kind="problem",
                detail=detail[:1000],
                source="company_audit",
                url=_first_url(audit.evidence_urls),
            )
        for idx, opp in enumerate(audit.opportunities or []):
            if not isinstance(opp, dict):
                continue
            title = str(opp.get("title") or opp.get("detail") or "").strip()
            if not title:
                continue
            detail = title
            if opp.get("detail"):
                detail = f"{title}: {opp.get('detail')}"
            _add(
                catalog,
                evidence_id=f"audit.opportunity.{idx}",
                kind="opportunity",
                detail=detail[:1000],
                source="company_audit",
                url=_first_url(audit.evidence_urls),
            )
        for idx, item in enumerate(audit.evidence_catalog or []):
            if not isinstance(item, dict):
                continue
            eid = str(item.get("evidence_id") or "").strip()
            detail = str(item.get("detail") or item.get("excerpt") or "").strip()
            if not eid or not detail:
                continue
            _add(
                catalog,
                evidence_id=f"audit.catalog.{eid}"[:64],
                kind=str(item.get("kind") or "audit_evidence")[:64],
                detail=detail,
                source="company_audit",
                url=item.get("url"),
            )

    return catalog


def catalog_index(catalog: list[SalesEvidenceItem]) -> dict[str, SalesEvidenceItem]:
    return {item.evidence_id: item for item in catalog}


def input_snapshot(
    *,
    company: Company,
    lead: Lead,
    score: CompanyScore | None,
    audit: CompanyAudit | None,
) -> dict[str, Any]:
    return {
        "company": {
            "id": str(company.id),
            "name": company.name,
            "website": company.website,
            "industry": company.industry,
            "location": company.location,
        },
        "lead": {
            "id": str(lead.id),
            "name": lead.name,
            "email": lead.email,
            "job_title": lead.job_title,
        },
        "score": None
        if score is None
        else {
            "id": str(score.id),
            "total_score": score.total_score,
            "band": score.band.value if hasattr(score.band, "value") else str(score.band),
        },
        "audit": None
        if audit is None
        else {
            "id": str(audit.id),
            "website_available": audit.website_available,
            "priority": audit.priority.value
            if hasattr(audit.priority, "value")
            else str(audit.priority),
            "problem_count": len(audit.problems or []),
            "opportunity_count": len(audit.opportunities or []),
            "has_recommended_solution": bool(audit.recommended_solution),
        },
    }


def _first_url(urls: list[str] | None) -> str | None:
    if not urls:
        return None
    for url in urls:
        if url and str(url).strip():
            return str(url).strip()
    return None
