"""Browser request-route SSRF decisions — testable without Playwright."""

from __future__ import annotations

from app.providers.browser.exceptions import BrowserUnsafeURLError
from app.providers.browser.url_policy import validate_browser_url


UNSAFE_SCHEMES = ("file:", "javascript:", "data:", "blob:", "ftp:")


def should_abort_browser_request(url: str, resource_type: str) -> bool:
    """Return True when the browser must abort this network request.

    Phase 20: ALL http(s) subresources (xhr/fetch/img/script/…) are SSRF-checked,
    not only document navigations. Downloads and non-http schemes always abort.
    """
    if resource_type == "download":
        return True
    lower = (url or "").lower()
    if lower.startswith(UNSAFE_SCHEMES):
        return True
    # About:blank and empty — allow (no network)
    if not lower or lower.startswith("about:"):
        return False
    if lower.startswith("http://") or lower.startswith("https://"):
        try:
            validate_browser_url(url, check_dns=True)
        except BrowserUnsafeURLError:
            return True
        return False
    # Unknown schemes — fail closed
    return True
