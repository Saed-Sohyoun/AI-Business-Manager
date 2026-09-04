"""Safe email logging — never log API keys, full bodies, or secrets."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.providers.email")


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def log_email_started(*, provider: str, to_email: str, subject: str, attempt: int) -> None:
    logger.info(
        "email_send_started provider=%s to=%s subject_len=%s attempt=%s",
        provider,
        _mask_email(to_email),
        len(subject or ""),
        attempt,
    )


def log_email_succeeded(
    *,
    provider: str,
    to_email: str,
    message_id: str,
    latency_ms: float,
    attempts: int,
    estimated_cost: Any,
) -> None:
    logger.info(
        "email_send_succeeded provider=%s to=%s message_id=%s latency_ms=%.1f "
        "attempts=%s estimated_cost=%s",
        provider,
        _mask_email(to_email),
        message_id,
        latency_ms,
        attempts,
        estimated_cost,
    )


def log_email_failed(
    *,
    provider: str,
    to_email: str,
    attempt: int,
    error_code: str,
    error_type: str,
) -> None:
    logger.warning(
        "email_send_failed provider=%s to=%s attempt=%s code=%s error=%s",
        provider,
        _mask_email(to_email),
        attempt,
        error_code,
        error_type,
    )
