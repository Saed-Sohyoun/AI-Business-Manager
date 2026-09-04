"""Build scoring facts from company memory — never invents missing signals."""

from __future__ import annotations

from app.models.company import Company
from app.models.company_evidence import CompanyEvidence
from app.models.company_source import CompanySource
from app.scoring.schemas import CompanyScoringFacts


def build_scoring_facts(
    company: Company,
    *,
    sources: list[CompanySource] | None = None,
    evidence: list[CompanyEvidence] | None = None,
    has_contact_page: bool = False,
    has_contact_form: bool = False,
    has_booking_or_calendar: bool = False,
) -> CompanyScoringFacts:
    source_list = sources if sources is not None else list(company.sources or [])
    evidence_list = evidence if evidence is not None else list(company.evidence or [])

    by_field: dict[str, CompanyEvidence] = {}
    for item in evidence_list:
        # Prefer verified over unverified when multiple rows exist
        current = by_field.get(item.field_name)
        if current is None:
            by_field[item.field_name] = item
            continue
        rank = {"verified": 2, "unverified": 1, "unknown": 0}
        if rank.get(item.verification_status, 0) > rank.get(current.verification_status, 0):
            by_field[item.field_name] = item

    website_ev = by_field.get("website")
    website_verified = bool(
        website_ev and website_ev.verification_status == "verified" and website_ev.field_value
    )
    website_value = company.website or (website_ev.field_value if website_ev else None)
    has_website = bool(website_value or company.website_domain)
    website_https = bool(website_value and str(website_value).lower().startswith("https://"))

    description = company.description
    desc_ev = by_field.get("description")
    if not description and desc_ev and desc_ev.field_value:
        description = desc_ev.field_value

    industry = company.industry
    ind_ev = by_field.get("industry")
    if not industry and ind_ev and ind_ev.field_value:
        industry = ind_ev.field_value

    location = company.location
    loc_ev = by_field.get("location")
    if not location and loc_ev and loc_ev.field_value:
        location = loc_ev.field_value

    def _has_value(field: str) -> bool:
        item = by_field.get(field)
        return bool(item and item.field_value and item.verification_status != "unknown")

    return CompanyScoringFacts(
        has_website=has_website,
        website_verified=website_verified,
        website_https=website_https,
        has_description=bool(description and description.strip()),
        description_length=len(description.strip()) if description else 0,
        source_count=len(source_list),
        has_industry=bool(industry and str(industry).strip()),
        has_location=bool(location and str(location).strip()),
        has_email_evidence=_has_value("email"),
        has_phone_evidence=_has_value("phone"),
        has_address_evidence=_has_value("address"),
        has_contact_page=has_contact_page,
        has_contact_form=has_contact_form,
        has_booking_or_calendar=has_booking_or_calendar,
        industry=industry,
        description=description,
        company_status=str(company.status.value if hasattr(company.status, "value") else company.status),
    )
