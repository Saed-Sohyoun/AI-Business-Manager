"""Playwright adapter implementing BrowserProvider.

This is the only module that may import Playwright.

Security posture:
- http/https only, no URL credentials
- SSRF host/DNS checks before navigation
- no downloads, no shell, no user-supplied JS evaluation
- bounded text/links/metadata
- all content marked untrusted
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from app.config import Settings
from app.providers.browser.base import BrowserProvider
from app.providers.browser.exceptions import (
    BrowserConfigurationError,
    BrowserNavigationError,
    BrowserPageTooLargeError,
    BrowserTimeoutError,
    BrowserUnsafeURLError,
)
from app.providers.browser.extraction import (
    EXTRACT_LINKS_JS,
    EXTRACT_META_JS,
    RawLink,
    RawPageExtraction,
    limit_links,
    limit_metadata,
    parse_content_length,
    truncate_text,
)
from app.providers.browser.safe_logging import (
    log_fetch_failed,
    log_fetch_started,
    log_fetch_succeeded,
)
from app.providers.browser.request_guard import should_abort_browser_request
from app.providers.browser.types import BrowserFetchRequest, BrowserLink, BrowserPageSnapshot
from app.providers.browser.url_policy import (
    is_safe_extracted_link,
    page_domain,
    validate_browser_url,
)


class PageNavigator(Protocol):
    """Injectable navigation backend (Playwright or test double)."""

    def fetch(self, url: str, *, settings: Settings) -> RawPageExtraction: ...


class PlaywrightNavigator:
    """Real Playwright navigation — fixed extraction scripts only."""

    def fetch(self, url: str, *, settings: Settings) -> RawPageExtraction:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserConfigurationError(
                "Playwright is not installed. Install backend requirements and browsers.",
                details={"provider": "playwright"},
            ) from exc

        nav_timeout_ms = int(settings.browser_navigation_timeout_seconds * 1000)
        op_timeout_ms = int(settings.browser_timeout_seconds * 1000)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=settings.browser_headless)
                try:
                    context = browser.new_context(
                        accept_downloads=False,
                        java_script_enabled=bool(settings.browser_javascript_enabled),
                        bypass_csp=False,
                        # Never persist storage/credentials
                        storage_state=None,
                    )
                    context.set_default_timeout(op_timeout_ms)
                    context.set_default_navigation_timeout(nav_timeout_ms)
                    page = context.new_page()

                    # Block downloads, unsafe schemes, and SSRF targets for ALL resource types
                    def _route_handler(route: Any) -> None:
                        request = route.request
                        if should_abort_browser_request(request.url, request.resource_type):
                            route.abort()
                            return
                        route.continue_()

                    page.route("**/*", _route_handler)

                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=nav_timeout_ms,
                    )
                    if response is None:
                        raise BrowserNavigationError(
                            "Navigation produced no response",
                            details={"url": url},
                        )

                    redirect_count = _count_redirects(response)
                    if redirect_count > settings.browser_max_redirects:
                        raise BrowserNavigationError(
                            "Too many redirects during navigation",
                            details={
                                "redirect_count": redirect_count,
                                "max_redirects": settings.browser_max_redirects,
                            },
                        )

                    content_length = parse_content_length(response.headers)
                    if (
                        content_length is not None
                        and content_length > settings.browser_max_page_size_bytes
                    ):
                        raise BrowserPageTooLargeError(
                            "Page Content-Length exceeds configured maximum",
                            details={
                                "content_length": content_length,
                                "max_page_size_bytes": settings.browser_max_page_size_bytes,
                            },
                        )

                    final_url = page.url
                    # Re-validate final URL after redirects (SSRF / scheme escape)
                    validate_browser_url(final_url, check_dns=True)

                    title = page.title() or ""
                    visible_text = ""
                    try:
                        visible_text = page.inner_text("body", timeout=op_timeout_ms) or ""
                    except PlaywrightError:
                        visible_text = ""

                    raw_links: list[RawLink] = []
                    try:
                        extracted = page.eval_on_selector_all("a[href]", EXTRACT_LINKS_JS)
                        if isinstance(extracted, list):
                            for item in extracted:
                                if not isinstance(item, dict):
                                    continue
                                href = item.get("href")
                                text = item.get("text") or ""
                                if isinstance(href, str):
                                    raw_links.append(
                                        RawLink(url=href, text=str(text)[:200])
                                    )
                    except PlaywrightError:
                        raw_links = []

                    page_metadata: dict[str, str] = {}
                    try:
                        meta = page.eval_on_selector_all("meta", EXTRACT_META_JS)
                        if isinstance(meta, dict):
                            page_metadata = {
                                str(k): str(v)
                                for k, v in meta.items()
                                if isinstance(k, str) and isinstance(v, str)
                            }
                    except PlaywrightError:
                        page_metadata = {}

                    return RawPageExtraction(
                        requested_url=url,
                        final_url=final_url,
                        title=title,
                        visible_text=visible_text,
                        links=raw_links,
                        page_metadata=page_metadata,
                        status_code=response.status,
                        redirect_count=redirect_count,
                        content_length=content_length,
                    )
                finally:
                    browser.close()
        except BrowserConfigurationError:
            raise
        except BrowserUnsafeURLError:
            raise
        except BrowserPageTooLargeError:
            raise
        except BrowserNavigationError:
            raise
        except PlaywrightTimeoutError as exc:
            raise BrowserTimeoutError(
                "Playwright navigation or extraction timed out",
                details={"provider": "playwright"},
            ) from exc
        except PlaywrightError as exc:
            raise BrowserNavigationError(
                "Playwright navigation failed",
                details={"provider": "playwright", "error_type": type(exc).__name__},
            ) from exc


def _count_redirects(response: Any) -> int:
    """Count redirects via Playwright request.redirected_from chain."""
    count = 0
    request = getattr(response, "request", None)
    while request is not None:
        redirected_from = getattr(request, "redirected_from", None)
        if redirected_from is None:
            break
        count += 1
        request = redirected_from
        if count > 50:
            break
    return count


class PlaywrightBrowserProvider(BrowserProvider):
    name = "playwright"

    def __init__(
        self,
        settings: Settings,
        *,
        navigator: PageNavigator | None = None,
        resolve: Callable[[str], list[str]] | None = None,
        check_dns: bool = True,
    ) -> None:
        self._settings = settings
        self._navigator = navigator or PlaywrightNavigator()
        self._resolve = resolve
        self._check_dns = check_dns

    def is_available(self) -> bool:
        if not self._settings.browser_enabled:
            return False
        if not isinstance(self._navigator, PlaywrightNavigator):
            # Injected test navigator counts as available
            return True
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False
        return True

    def fetch(self, request: BrowserFetchRequest) -> BrowserPageSnapshot:
        execution_id = str(uuid.uuid4())
        log_fetch_started(
            provider=self.name,
            request=request,
            execution_id=execution_id,
        )

        if not self._settings.browser_enabled:
            error = BrowserConfigurationError(
                "Browser provider is disabled (BROWSER_ENABLED=false)",
                details={"provider": self.name},
            )
            log_fetch_failed(
                provider=self.name,
                execution_id=execution_id,
                error_code=error.code,
                error_type=type(error).__name__,
                metadata=request.metadata,
            )
            raise error

        if not self.is_available():
            error = BrowserConfigurationError(
                "Browser provider is unavailable — Playwright is not installed",
                details={"provider": self.name},
            )
            log_fetch_failed(
                provider=self.name,
                execution_id=execution_id,
                error_code=error.code,
                error_type=type(error).__name__,
                metadata=request.metadata,
            )
            raise error

        started = time.perf_counter()
        try:
            safe_url = validate_browser_url(
                request.url,
                resolve=self._resolve,
                check_dns=self._check_dns,
            )
            raw = self._navigator.fetch(safe_url, settings=self._settings)
            # Validate final URL again at provider boundary
            final_safe = validate_browser_url(
                raw.final_url,
                resolve=self._resolve,
                check_dns=self._check_dns,
            )
            if raw.redirect_count > self._settings.browser_max_redirects:
                raise BrowserNavigationError(
                    "Too many redirects during navigation",
                    details={
                        "redirect_count": raw.redirect_count,
                        "max_redirects": self._settings.browser_max_redirects,
                    },
                )
            if (
                raw.content_length is not None
                and raw.content_length > self._settings.browser_max_page_size_bytes
            ):
                raise BrowserPageTooLargeError(
                    "Page exceeds maximum allowed size",
                    details={
                        "content_length": raw.content_length,
                        "max_page_size_bytes": self._settings.browser_max_page_size_bytes,
                    },
                )

            snapshot = self._to_snapshot(
                request=request,
                raw=raw,
                final_url=final_safe,
                execution_id=execution_id,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            log_fetch_succeeded(snapshot=snapshot)
            return snapshot
        except (
            BrowserConfigurationError,
            BrowserUnsafeURLError,
            BrowserTimeoutError,
            BrowserNavigationError,
            BrowserPageTooLargeError,
        ) as exc:
            log_fetch_failed(
                provider=self.name,
                execution_id=execution_id,
                error_code=exc.code,
                error_type=type(exc).__name__,
                metadata=request.metadata,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            log_fetch_failed(
                provider=self.name,
                execution_id=execution_id,
                error_code="browser_error",
                error_type=type(exc).__name__,
                metadata=request.metadata,
            )
            raise BrowserNavigationError(
                "Unexpected browser failure",
                details={"provider": self.name, "error_type": type(exc).__name__},
            ) from exc

    def _to_snapshot(
        self,
        *,
        request: BrowserFetchRequest,
        raw: RawPageExtraction,
        final_url: str,
        execution_id: str,
        latency_ms: float,
    ) -> BrowserPageSnapshot:
        text = ""
        text_truncated = False
        if request.include_text:
            text, text_truncated = truncate_text(
                raw.visible_text or "",
                self._settings.browser_max_text_chars,
            )

        links: list[BrowserLink] = []
        links_truncated = False
        if request.include_links:
            safe_raw: list[RawLink] = []
            for link in raw.links:
                if is_safe_extracted_link(link.url):
                    safe_raw.append(link)
            limited, links_truncated = limit_links(
                safe_raw,
                self._settings.browser_max_links,
            )
            links = [
                BrowserLink(url=item.url, text=item.text, trust_level="untrusted")
                for item in limited
            ]

        page_metadata: dict[str, str] = {}
        metadata_truncated = False
        if request.include_metadata:
            page_metadata, metadata_truncated = limit_metadata(
                raw.page_metadata or {},
                self._settings.browser_max_metadata_items,
            )

        return BrowserPageSnapshot(
            requested_url=request.url,
            final_url=final_url,
            title=(raw.title or "")[:500],
            visible_text=text,
            links=links,
            page_metadata=page_metadata,
            status_code=raw.status_code,
            redirect_count=raw.redirect_count,
            domain=page_domain(final_url),
            text_truncated=text_truncated,
            links_truncated=links_truncated,
            metadata_truncated=metadata_truncated,
            content_length=raw.content_length,
            latency_ms=latency_ms,
            execution_id=execution_id,
            provider=self.name,
            metadata=dict(request.metadata),
            trust_level="untrusted",
            untrusted_content=True,
        )
