"""Authenticate inbound n8n webhook requests."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings, get_settings
from app.exceptions import UnauthorizedError
from app.security import constant_time_equals, validate_webhook_timestamp


HEADER_NAME = "X-N8N-Webhook-Secret"
TIMESTAMP_HEADER = "X-N8N-Timestamp"


def verify_n8n_webhook(request: Request, settings: Settings | None = None) -> None:
    """Fail closed when secret missing, timestamp skew invalid, or credentials mismatch."""
    cfg = settings or getattr(request.app.state, "settings", None) or get_settings()
    if not cfg.n8n_webhook_configured:
        raise UnauthorizedError(
            "n8n webhook secret is not configured",
            details={"hint": "Set N8N_WEBHOOK_SECRET"},
        )

    if cfg.n8n_webhook_require_timestamp:
        validate_webhook_timestamp(
            request.headers.get(TIMESTAMP_HEADER),
            max_skew_seconds=cfg.n8n_webhook_max_skew_seconds,
        )

    expected = cfg.n8n_webhook_secret.get_secret_value().strip()  # type: ignore[union-attr]
    header_name = (cfg.n8n_webhook_header or HEADER_NAME).strip() or HEADER_NAME
    provided = (request.headers.get(header_name) or "").strip()

    if not provided:
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()

    if not provided or not constant_time_equals(provided, expected):
        raise UnauthorizedError("Invalid n8n webhook credentials")
