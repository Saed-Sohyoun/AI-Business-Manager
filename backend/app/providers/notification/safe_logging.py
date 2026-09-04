"""Safe notification logging — never log bot tokens, chat secrets, or full bodies."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.providers.notification")


def log_notification_started(
    *,
    provider: str,
    priority: str,
    category: str,
    title_len: int,
    attempt: int,
) -> None:
    logger.info(
        "notification_send_started provider=%s priority=%s category=%s "
        "title_len=%s attempt=%s",
        provider,
        priority,
        category,
        title_len,
        attempt,
    )


def log_notification_succeeded(
    *,
    provider: str,
    priority: str,
    category: str,
    message_id: str,
    latency_ms: float,
    attempts: int,
) -> None:
    logger.info(
        "notification_send_succeeded provider=%s priority=%s category=%s "
        "message_id=%s latency_ms=%.1f attempts=%s",
        provider,
        priority,
        category,
        message_id,
        latency_ms,
        attempts,
    )


def log_notification_failed(
    *,
    provider: str,
    priority: str,
    category: str,
    attempt: int,
    error_code: str,
    error_type: str,
) -> None:
    logger.warning(
        "notification_send_failed provider=%s priority=%s category=%s "
        "attempt=%s code=%s error=%s",
        provider,
        priority,
        category,
        attempt,
        error_code,
        error_type,
    )


def redact_secrets(text: str, *, token: str | None = None) -> str:
    """Remove known secrets from error strings before logging/storing."""
    cleaned = text
    if token:
        cleaned = cleaned.replace(token, "***")
    # Common Telegram URL leak pattern
    if "/bot" in cleaned:
        parts = cleaned.split("/bot", 1)
        if len(parts) == 2 and "/" in parts[1]:
            rest = parts[1].split("/", 1)[1]
            cleaned = f"{parts[0]}/bot***/{rest}"
        else:
            cleaned = cleaned.replace("/bot", "/bot***")
    return cleaned


def log_safe_event(event: str, **fields: Any) -> None:
    logger.info("notification_%s %s", event, " ".join(f"{k}={v}" for k, v in fields.items()))
