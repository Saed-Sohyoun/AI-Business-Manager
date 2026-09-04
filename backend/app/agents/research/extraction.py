"""Deterministic candidate extraction from search/browser evidence.

Never invents facts. Only maps observed provider data into structured fields.
"""

from __future__ import annotations

import re

from app.agents.research.schemas import ResearchCandidate, ResearchField
from app.providers.search.types import SearchResult
from app.providers.search.url_utils import extract_domain, is_allowed_url, normalize_url

# Domains that are directories/platforms — not target businesses for Phase 5 pilot.
NON_COMPANY_DOMAINS = frozenset(
    {
        "google.com",
        "bing.com",
        "yahoo.com",
        "duckduckgo.com",
        "youtube.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "wikipedia.org",
        "yelp.com",
        "tripadvisor.com",
        "amazon.com",
        "apple.com",
        "play.google.com",
        "maps.google.com",
    }
)

_TITLE_SPLIT = re.compile(r"\s+[|\-–—:]\s+")


def registrable_domain(url: str) -> str | None:
    if not is_allowed_url(url):
        return None
    host = extract_domain(url)
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    # Drop common multi-part noise for simple cases (keep last two labels)
    parts = host.split(".")
    if len(parts) >= 2:
        # keep full host for uniqueness (subdomains often are the company site)
        return host
    return host


def homepage_url(domain: str) -> str:
    return f"https://{domain}/"


def is_non_company_domain(domain: str) -> bool:
    lowered = domain.lower()
    if lowered in NON_COMPANY_DOMAINS:
        return True
    return any(lowered.endswith(f".{blocked}") for blocked in NON_COMPANY_DOMAINS)


def name_from_title(title: str | None, domain: str | None) -> ResearchField:
    """Extract a display name only from an observed title string.

    Does not invent names from domains — missing titles stay unknown.
    """
    del domain  # reserved for future verified brand signals; never used to invent
    if not title or not title.strip():
        return ResearchField(value=None, status="unknown")
    cleaned = title.strip()
    parts = _TITLE_SPLIT.split(cleaned, maxsplit=1)
    name = parts[0].strip() if parts else cleaned
    name = re.sub(r"\s+", " ", name)[:255]
    if not name:
        return ResearchField(value=None, status="unknown")
    return ResearchField(value=name, status="unverified")


def candidate_from_search_result(result: SearchResult) -> ResearchCandidate | None:
    """Build a candidate strictly from a search hit. Returns None if unusable."""
    if not is_allowed_url(result.url):
        return ResearchCandidate(
            name=ResearchField(status="unknown"),
            website=ResearchField(status="unknown"),
            skipped_reason="invalid_url",
            source_urls=[result.url] if result.url else [],
        )

    domain = registrable_domain(result.url)
    if not domain:
        return ResearchCandidate(
            name=ResearchField(status="unknown"),
            website=ResearchField(status="unknown"),
            skipped_reason="invalid_url",
            source_urls=[result.url],
        )

    if is_non_company_domain(domain):
        return ResearchCandidate(
            name=ResearchField(status="unknown"),
            website=ResearchField(value=homepage_url(domain), status="unverified", source_url=result.url),
            website_domain=domain,
            skipped_reason="non_company_domain",
            source_urls=[result.url],
        )

    website = homepage_url(domain)
    name = name_from_title(result.title, domain)
    if name.source_url is None:
        name = ResearchField(value=name.value, status=name.status, source_url=result.url)

    description = ResearchField(status="unknown")
    if result.snippet and result.snippet.strip():
        description = ResearchField(
            value=result.snippet.strip()[:2000],
            status="unverified",
            source_url=result.url,
        )

    return ResearchCandidate(
        name=name,
        website=ResearchField(value=website, status="unverified", source_url=result.url),
        website_domain=domain,
        description=description,
        industry=ResearchField(status="unknown"),
        location=ResearchField(status="unknown"),
        email=ResearchField(status="unknown"),
        phone=ResearchField(status="unknown"),
        address=ResearchField(status="unknown"),
        source_urls=[result.url],
    )


def apply_browser_verification(
    candidate: ResearchCandidate,
    *,
    final_url: str,
    page_title: str,
    meta_description: str | None,
    page_source_url: str,
) -> ResearchCandidate:
    """Upgrade fields only from observed browser page data on the candidate domain."""
    if not candidate.website_domain:
        return candidate

    final_domain = registrable_domain(final_url)
    if not final_domain or final_domain != candidate.website_domain:
        # Do not accept cross-domain redirect content as verification
        return candidate

    website = ResearchField(
        value=homepage_url(candidate.website_domain),
        status="verified",
        source_url=page_source_url,
    )

    name = candidate.name
    if (not name.value) and page_title.strip():
        name = name_from_title(page_title, candidate.website_domain)
        name = ResearchField(value=name.value, status="unverified", source_url=page_source_url)
    elif name.value and page_title.strip():
        # Keep existing name; mark verified only if title contains it (observed)
        if name.value.lower() in page_title.lower():
            name = ResearchField(value=name.value, status="verified", source_url=page_source_url)

    description = candidate.description
    if (not description.value) and meta_description and meta_description.strip():
        description = ResearchField(
            value=meta_description.strip()[:2000],
            status="unverified",
            source_url=page_source_url,
        )

    sources = list(candidate.source_urls)
    if page_source_url not in sources:
        sources.append(page_source_url)

    return candidate.model_copy(
        update={
            "website": website,
            "name": name,
            "description": description,
            "source_urls": sources,
        }
    )


def normalized_source(url: str) -> str | None:
    return normalize_url(url) or (url.strip() if url else None)
