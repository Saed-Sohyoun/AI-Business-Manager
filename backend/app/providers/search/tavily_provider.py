"""Tavily adapter implementing SearchProvider.

Uses httpx against the Tavily HTTP API. This is the only module that should
know Tavily-specific request/response shapes. Business logic must depend on
SearchProvider / SearchService instead.

All result content is UNTRUSTED DATA.
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from app.config import Settings
from app.providers.search.base import SearchProvider
from app.providers.search.costing import estimate_search_cost
from app.providers.search.exceptions import (
    SearchConfigurationError,
    SearchMalformedResponseError,
    SearchProviderError,
    SearchRateLimitError,
    SearchTimeoutError,
)
from app.providers.search.safe_logging import (
    log_search_failed,
    log_search_started,
    log_search_succeeded,
)
from app.providers.search.types import SearchRequest, SearchResponse, SearchResult
from app.providers.search.url_utils import extract_domain, is_allowed_url, normalize_url

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _retry_after_seconds(exc: BaseException, attempt: int) -> float:
    header_value: str | None = None
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        header_value = headers.get("retry-after") or headers.get("Retry-After")
    if header_value:
        try:
            return max(float(header_value), 0.1)
        except ValueError:
            pass
    base = min(2**attempt, 20)
    return base + random.uniform(0, 0.25)


class TavilySearchProvider(SearchProvider):
    """Tavily web search adapter with retries, normalization, and validation."""

    name = "tavily"

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        sleep_fn: Any | None = None,
        api_url: str = TAVILY_SEARCH_URL,
    ) -> None:
        self._settings = settings
        self._client = http_client
        self._owns_client = http_client is None
        self._sleep = sleep_fn or time.sleep
        self._api_url = api_url

    def is_configured(self) -> bool:
        return self._settings.tavily_configured

    def search(self, request: SearchRequest) -> SearchResponse:
        from app.exceptions import ServiceUnavailableError
        from app.providers.circuit_breaker import get_circuit

        circuit = get_circuit("search", failure_threshold=5, reset_timeout_seconds=30.0)
        if not circuit.allow_request():
            raise ServiceUnavailableError(
                "Research is temporarily unavailable",
                details={"code": "CIRCUIT_OPEN", "provider": "search"},
            )
        try:
            result = self._search_inner(request)
        except SearchConfigurationError:
            raise
        except Exception:
            circuit.record_failure()
            raise
        circuit.record_success()
        return result

    def _search_inner(self, request: SearchRequest) -> SearchResponse:
        if not self.is_configured():
            raise SearchConfigurationError(
                "TAVILY_API_KEY is not configured. Set it in the environment to use search.",
                details={"provider": self.name},
            )

        max_retries = self._settings.tavily_max_retries
        timeout = request.timeout_seconds or self._settings.tavily_timeout
        max_results = min(
            request.max_results or self._settings.tavily_max_results,
            self._settings.tavily_max_results,
        )
        depth = request.search_depth or self._settings.tavily_search_depth

        attempts = 0
        last_error: Exception | None = None
        client = self._ensure_client(timeout=timeout)

        while attempts <= max_retries:
            attempts += 1
            log_search_started(provider=self.name, request=request, attempt=attempts)
            started = time.perf_counter()
            try:
                payload = self._build_payload(
                    request=request,
                    max_results=max_results,
                    depth=depth,
                )
                response = client.post(self._api_url, json=payload, timeout=timeout)
                latency_ms = (time.perf_counter() - started) * 1000
                normalized = self._normalize_http_response(
                    response=response,
                    request=request,
                    max_results=max_results,
                    latency_ms=latency_ms,
                    attempts=attempts,
                )
                log_search_succeeded(response=normalized)
                return normalized
            except (
                SearchConfigurationError,
                SearchMalformedResponseError,
            ):
                raise
            except Exception as exc:  # noqa: BLE001 — mapped to typed search errors
                last_error = exc
                mapped = self._map_exception(exc)
                log_search_failed(
                    provider=self.name,
                    attempt=attempts,
                    error_code=mapped.code,
                    error_type=type(exc).__name__,
                    metadata=request.metadata,
                )
                retryable = isinstance(mapped, (SearchTimeoutError, SearchRateLimitError)) or (
                    isinstance(mapped, SearchProviderError)
                    and mapped.details.get("retryable") is True
                )
                if not retryable or attempts > max_retries:
                    raise mapped from exc
                self._sleep(_retry_after_seconds(exc, attempts))

        raise SearchProviderError(
            "Search provider request failed after retries",
            details={"attempts": attempts, "reason": str(last_error) if last_error else None},
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_client(self, *, timeout: float) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return self._client

    def _build_payload(
        self,
        *,
        request: SearchRequest,
        max_results: int,
        depth: str,
    ) -> dict[str, Any]:
        api_key = self._settings.tavily_api_key
        assert api_key is not None
        payload: dict[str, Any] = {
            "api_key": api_key.get_secret_value(),
            "query": request.query,
            "max_results": max_results,
            "search_depth": depth,
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
        }
        if request.include_domains:
            payload["include_domains"] = request.include_domains
        if request.exclude_domains:
            payload["exclude_domains"] = request.exclude_domains
        return payload

    def _normalize_http_response(
        self,
        *,
        response: httpx.Response,
        request: SearchRequest,
        max_results: int,
        latency_ms: float,
        attempts: int,
    ) -> SearchResponse:
        if response.status_code == 429:
            raise SearchRateLimitError(
                "Tavily rate limit exceeded",
                details={"provider": self.name, "status_code": 429, "retryable": True},
            )
        if response.status_code in {401, 403}:
            raise SearchConfigurationError(
                "Tavily authentication failed — check TAVILY_API_KEY",
                details={"provider": self.name, "status_code": response.status_code},
            )
        if response.status_code >= 500:
            raise SearchProviderError(
                "Tavily returned a server error",
                details={
                    "provider": self.name,
                    "status_code": response.status_code,
                    "retryable": True,
                },
            )
        if response.status_code >= 400:
            raise SearchProviderError(
                "Tavily rejected the search request",
                details={
                    "provider": self.name,
                    "status_code": response.status_code,
                    "retryable": False,
                },
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise SearchMalformedResponseError(
                "Tavily response was not valid JSON",
                details={"provider": self.name},
            ) from exc

        if not isinstance(data, dict):
            raise SearchMalformedResponseError(
                "Tavily response JSON must be an object",
                details={"provider": self.name},
            )

        raw_results = data.get("results")
        if raw_results is None:
            raise SearchMalformedResponseError(
                "Tavily response missing results field",
                details={"provider": self.name},
            )
        if not isinstance(raw_results, list):
            raise SearchMalformedResponseError(
                "Tavily results field must be a list",
                details={"provider": self.name},
            )

        results, duplicates_removed, invalid_removed = self._normalize_results(
            raw_results,
            max_results=max_results,
        )

        return SearchResponse(
            query=request.query,
            results=results,
            provider=self.name,
            result_count=len(results),
            duplicates_removed=duplicates_removed,
            invalid_urls_removed=invalid_removed,
            estimated_cost=estimate_search_cost(self._settings.tavily_cost_per_request),
            latency_ms=latency_ms,
            attempts=attempts,
            request_id=data.get("request_id") or response.headers.get("x-request-id"),
            metadata=dict(request.metadata),
            untrusted_content=True,
        )

    def _normalize_results(
        self,
        raw_results: list[Any],
        *,
        max_results: int,
    ) -> tuple[list[SearchResult], int, int]:
        seen: set[str] = set()
        normalized: list[SearchResult] = []
        duplicates = 0
        invalid = 0

        for item in raw_results:
            if not isinstance(item, dict):
                invalid += 1
                continue
            url = item.get("url")
            if not isinstance(url, str) or not is_allowed_url(url):
                invalid += 1
                continue
            normalized_url = normalize_url(url)
            if normalized_url is None:
                invalid += 1
                continue
            if normalized_url in seen:
                duplicates += 1
                continue
            seen.add(normalized_url)

            title = item.get("title")
            snippet = item.get("content") or item.get("snippet") or ""
            if not isinstance(title, str):
                title = ""
            if not isinstance(snippet, str):
                snippet = ""

            score = item.get("score")
            relevance: float | None
            try:
                relevance = float(score) if score is not None else None
            except (TypeError, ValueError):
                relevance = None

            source_metadata = {
                "raw_score": score,
                "published_date": item.get("published_date"),
                # Explicit trust marker for any consumer reading metadata
                "trust_level": "untrusted",
                "origin": "tavily",
            }

            normalized.append(
                SearchResult(
                    title=title.strip() or normalized_url,
                    url=url.strip(),
                    normalized_url=normalized_url,
                    snippet=snippet.strip(),
                    domain=extract_domain(normalized_url),
                    relevance_score=relevance,
                    source_metadata=source_metadata,
                    trust_level="untrusted",
                )
            )
            if len(normalized) >= max_results:
                break

        return normalized, duplicates, invalid

    def _map_exception(self, exc: Exception) -> Exception:
        if isinstance(
            exc,
            (
                SearchConfigurationError,
                SearchTimeoutError,
                SearchRateLimitError,
                SearchProviderError,
                SearchMalformedResponseError,
            ),
        ):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return SearchTimeoutError(
                "Tavily request timed out",
                details={"provider": self.name, "retryable": True},
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status == 429:
                return SearchRateLimitError(
                    "Tavily rate limit exceeded",
                    details={"provider": self.name, "status_code": 429, "retryable": True},
                )
            return SearchProviderError(
                "Tavily HTTP error",
                details={
                    "provider": self.name,
                    "status_code": status,
                    "retryable": status >= 500,
                },
            )
        if isinstance(exc, httpx.TransportError):
            return SearchProviderError(
                "Failed to connect to Tavily",
                details={"provider": self.name, "retryable": True},
            )
        return SearchProviderError(
            "Unexpected search provider failure",
            details={
                "provider": self.name,
                "error_type": type(exc).__name__,
                "retryable": False,
            },
        )
