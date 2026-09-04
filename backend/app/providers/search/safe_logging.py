"""Safe logging for search provider calls.

Never log API keys or full page/snippet content from search results.
"""

from __future__ import annotations

import logging
from typing import Any

from app.providers.search.types import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)

_SENSITIVE_METADATA_KEYS = {
    "email",
    "phone",
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "prompt",
    "content",
    "snippet",
    "query",
}


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_METADATA_KEYS):
            safe[key] = "[redacted]"
            continue
        if isinstance(value, str) and len(value) > 120:
            safe[key] = f"{value[:117]}..."
        else:
            safe[key] = value
    return safe


def log_search_started(*, provider: str, request: SearchRequest, attempt: int) -> None:
    logger.info(
        "Search started provider=%s attempt=%s query_chars=%s max_results=%s "
        "depth=%s metadata=%s",
        provider,
        attempt,
        len(request.query),
        request.max_results,
        request.search_depth,
        sanitize_metadata(request.metadata),
    )


def log_search_succeeded(*, response: SearchResponse) -> None:
    logger.info(
        "Search succeeded provider=%s request_id=%s latency_ms=%.1f attempts=%s "
        "result_count=%s duplicates_removed=%s invalid_urls_removed=%s "
        "estimated_cost=%s untrusted_content=%s metadata=%s",
        response.provider,
        response.request_id or "-",
        response.latency_ms,
        response.attempts,
        response.result_count,
        response.duplicates_removed,
        response.invalid_urls_removed,
        response.estimated_cost,
        response.untrusted_content,
        sanitize_metadata(response.metadata),
    )


def log_search_failed(
    *,
    provider: str,
    attempt: int,
    error_code: str,
    error_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    logger.warning(
        "Search failed provider=%s attempt=%s error_code=%s error_type=%s metadata=%s",
        provider,
        attempt,
        error_code,
        error_type,
        sanitize_metadata(metadata),
    )
