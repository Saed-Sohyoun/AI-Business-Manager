"""Centralized secret/PII redaction for logs and event details."""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "password_hash",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "session",
        "csrf",
        "webhook_secret",
        "owner_api_key",
        "x-owner-api-key",
        "body_html",
        "raw_payload",
    }
)


def redact_value(key: str, value: Any) -> Any:
    if key.lower().replace("-", "_") in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return redact_dict(value)
    if isinstance(value, list):
        return [redact_dict(v) if isinstance(v, dict) else v for v in value]
    return value


def redact_dict(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    return {k: redact_value(k, v) for k, v in data.items()}


def redact_text(text: str) -> str:
    """Best-effort string scrub for accidental key dumps."""
    lowered = text.lower()
    for needle in ("api_key", "authorization:", "password=", "bearer "):
        if needle in lowered:
            return "[REDACTED]"
    return text
