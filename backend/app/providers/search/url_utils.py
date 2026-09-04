"""URL validation, normalization, and search-result deduplication."""

from __future__ import annotations

import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking params commonly safe to strip for deduplication
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google.com",
        "instance-data",
    }
)


def is_allowed_url(url: str) -> bool:
    """Return True only for http(s) URLs with a real non-private host.

    Phase 20: IPv4 + IPv6 private/loopback/link-local blocked. Search results are
    never fetched by this module — this is a filter for untrusted result URLs.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"}:
        return False
    if not parts.netloc or parts.netloc.startswith("."):
        return False
    # Reject credentials in URL (unexpected for search results; suspicious)
    if "@" in parts.netloc and parts.username is not None:
        return False
    host = parts.hostname
    if not host:
        return False
    lowered = host.lower().strip(".")
    if lowered in _BLOCKED_HOSTS:
        return False
    if lowered.endswith(".localhost") or lowered.endswith(".local"):
        return False
    if lowered.endswith(".internal") or lowered.endswith(".intranet"):
        return False
    if _is_blocked_ip_literal(lowered):
        return False
    return True


def _is_blocked_ip_literal(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def normalize_url(url: str) -> str | None:
    """Normalize URL for comparison/storage, or None if invalid."""
    if not is_allowed_url(url):
        return None
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    # Drop default ports
    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = host
    elif port:
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parts.path or "/"
    # Collapse trailing slash except for root
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)

    # Drop fragment — not meaningful for identity
    return urlunsplit((scheme, netloc, path, query, ""))


def extract_domain(url: str) -> str:
    try:
        host = urlsplit(url).hostname
        return (host or "").lower()
    except ValueError:
        return ""
