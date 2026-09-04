"""URL safety policy for browser navigation (SSRF / scheme controls).

Stricter than search-result filtering: resolves hostnames when possible and
rejects private, loopback, link-local, and metadata targets.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from app.providers.browser.exceptions import BrowserUnsafeURLError
from app.providers.search.url_utils import extract_domain, normalize_url

ALLOWED_SCHEMES = frozenset({"http", "https"})
BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google.com",
        "instance-data",
    }
)

Resolver = Callable[[str], list[str]]


def _default_resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise BrowserUnsafeURLError(
            "URL hostname could not be resolved",
            details={"host": host, "reason": str(exc)},
        ) from exc
    addresses: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in addresses:
            addresses.append(addr)
    return addresses


def _is_blocked_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
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


def _host_blocked(host: str) -> bool:
    lowered = host.lower().strip(".")
    if lowered in BLOCKED_HOSTS:
        return True
    if lowered.endswith(".localhost") or lowered.endswith(".local"):
        return True
    if lowered.endswith(".internal") or lowered.endswith(".intranet"):
        return True
    # Literal IP in hostname
    return _is_blocked_ip(lowered)


def validate_browser_url(
    url: str,
    *,
    resolve: Resolver | None = None,
    check_dns: bool = True,
) -> str:
    """Validate and normalize a URL for browser navigation.

    Raises BrowserUnsafeURLError on unsafe schemes, credentials, private hosts,
    or DNS resolution to non-public addresses.
    Returns a normalized URL string.
    """
    if not url or not isinstance(url, str):
        raise BrowserUnsafeURLError("URL is required")

    candidate = url.strip()
    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise BrowserUnsafeURLError("URL could not be parsed") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise BrowserUnsafeURLError(
            "Only http and https URLs are allowed",
            details={"scheme": scheme or None},
        )

    # No credentials — browsers must not handle login material via URL
    if parts.username is not None or parts.password is not None:
        raise BrowserUnsafeURLError(
            "URLs with embedded credentials are not allowed",
            details={"reason": "credentials_forbidden"},
        )

    host = parts.hostname
    if not host:
        raise BrowserUnsafeURLError("URL must include a hostname")

    if _host_blocked(host):
        raise BrowserUnsafeURLError(
            "URL host is not allowed for browser navigation",
            details={"host": host.lower()},
        )

    if check_dns:
        resolver = resolve or _default_resolve
        # If host is already an IP literal, validate directly
        try:
            ipaddress.ip_address(host)
            addresses = [host]
        except ValueError:
            addresses = resolver(host)
        if not addresses:
            raise BrowserUnsafeURLError(
                "URL hostname resolved to no addresses",
                details={"host": host},
            )
        for addr in addresses:
            if _is_blocked_ip(addr):
                raise BrowserUnsafeURLError(
                    "URL resolves to a non-public address",
                    details={"host": host, "address": addr},
                )

    normalized = normalize_url(candidate)
    if normalized is None:
        # normalize_url uses search allowlist; if it fails after our checks, reject
        raise BrowserUnsafeURLError(
            "URL failed normalization safety checks",
            details={"host": host},
        )
    return normalized


def is_safe_extracted_link(url: str) -> bool:
    """Soft check for links found on a page (no DNS — keep extraction bounded)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        return False
    if parts.username is not None or parts.password is not None:
        return False
    host = parts.hostname
    if not host or _host_blocked(host):
        return False
    return True


def page_domain(url: str) -> str:
    return extract_domain(url)
