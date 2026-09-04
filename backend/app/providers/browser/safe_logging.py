"""Safe logging for browser operations — never log page body content."""

from __future__ import annotations

import logging
from typing import Any

from app.providers.browser.types import BrowserFetchRequest, BrowserPageSnapshot

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {
    "email",
    "phone",
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "cookie",
    "content",
    "text",
    "html",
    "body",
}


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_KEYS):
            safe[key] = "[redacted]"
            continue
        if isinstance(value, str) and len(value) > 120:
            safe[key] = f"{value[:117]}..."
        else:
            safe[key] = value
    return safe


def log_fetch_started(*, provider: str, request: BrowserFetchRequest, execution_id: str) -> None:
    logger.info(
        "Browser fetch started provider=%s execution_id=%s url_chars=%s "
        "include_text=%s include_links=%s include_metadata=%s metadata=%s",
        provider,
        execution_id,
        len(request.url),
        request.include_text,
        request.include_links,
        request.include_metadata,
        sanitize_metadata(request.metadata),
    )


def log_fetch_succeeded(*, snapshot: BrowserPageSnapshot) -> None:
    logger.info(
        "Browser fetch succeeded provider=%s execution_id=%s domain=%s "
        "latency_ms=%.1f status_code=%s redirect_count=%s text_chars=%s "
        "links=%s text_truncated=%s untrusted_content=%s metadata=%s",
        snapshot.provider,
        snapshot.execution_id,
        snapshot.domain,
        snapshot.latency_ms,
        snapshot.status_code,
        snapshot.redirect_count,
        len(snapshot.visible_text),
        len(snapshot.links),
        snapshot.text_truncated,
        snapshot.untrusted_content,
        sanitize_metadata(snapshot.metadata),
    )


def log_fetch_failed(
    *,
    provider: str,
    execution_id: str,
    error_code: str,
    error_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    logger.warning(
        "Browser fetch failed provider=%s execution_id=%s error_code=%s "
        "error_type=%s metadata=%s",
        provider,
        execution_id,
        error_code,
        error_type,
        sanitize_metadata(metadata),
    )
