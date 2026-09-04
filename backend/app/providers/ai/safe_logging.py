"""Safe logging helpers for AI provider calls.

Never log API keys, full prompts, or sensitive user content.
"""

from __future__ import annotations

import logging
from typing import Any

from app.providers.ai.types import AICompletionRequest, AIResponse

logger = logging.getLogger(__name__)

_SENSITIVE_METADATA_KEYS = {
    "email",
    "phone",
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "ssn",
    "prompt",
    "content",
    "message",
    "user_message",
    "system_instruction",
}


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return metadata safe for logs (drop sensitive keys, truncate values)."""
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


def log_completion_started(
    *,
    provider: str,
    model: str,
    request: AICompletionRequest,
    attempt: int,
) -> None:
    logger.info(
        "AI completion started provider=%s model=%s attempt=%s structured=%s "
        "user_chars=%s system_chars=%s metadata=%s",
        provider,
        model,
        attempt,
        request.json_schema is not None,
        len(request.user_message),
        len(request.system_instruction or ""),
        sanitize_metadata(request.metadata),
    )


def log_completion_succeeded(*, response: AIResponse) -> None:
    logger.info(
        "AI completion succeeded provider=%s model=%s request_id=%s "
        "latency_ms=%.1f attempts=%s input_tokens=%s output_tokens=%s "
        "estimated_cost=%s metadata=%s",
        response.provider,
        response.model,
        response.request_id or "-",
        response.latency_ms,
        response.attempts,
        response.input_tokens,
        response.output_tokens,
        response.estimated_cost,
        sanitize_metadata(response.metadata),
    )


def log_completion_failed(
    *,
    provider: str,
    model: str,
    attempt: int,
    error_code: str,
    error_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    logger.warning(
        "AI completion failed provider=%s model=%s attempt=%s "
        "error_code=%s error_type=%s metadata=%s",
        provider,
        model,
        attempt,
        error_code,
        error_type,
        sanitize_metadata(metadata),
    )
