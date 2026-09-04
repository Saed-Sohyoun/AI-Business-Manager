"""Authenticate inbound n8n webhook requests (HMAC + timestamp + nonce replay)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.exceptions import UnauthorizedError
from app.models.base import utc_now
from app.models.webhook_nonce import WebhookNonce
from app.security import constant_time_equals, validate_webhook_timestamp
from app.security.events import (
    WEBHOOK_REPLAY_REJECTED,
    WEBHOOK_SIGNATURE_INVALID,
    record_security_event,
)

logger = logging.getLogger(__name__)

HEADER_NAME = "X-N8N-Webhook-Secret"
TIMESTAMP_HEADER = "X-N8N-Timestamp"
SIGNATURE_HEADER = "X-N8N-Signature"
NONCE_HEADER = "X-N8N-Nonce"


def build_n8n_signing_string(
    *,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
) -> bytes:
    """Canonical string: timestamp.METHOD.path.body"""
    return f"{timestamp}.{method.upper()}.{path}.".encode("utf-8") + body


def sign_n8n_request(
    *,
    secret: str,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        build_n8n_signing_string(
            timestamp=timestamp, method=method, path=path, body=body
        ),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


async def verify_n8n_webhook(
    request: Request,
    settings: Settings | None = None,
    *,
    session: Session | None = None,
) -> None:
    """Fail closed: secret, timestamp, HMAC signature, nonce replay."""
    cfg = settings or getattr(request.app.state, "settings", None) or get_settings()
    if not cfg.n8n_webhook_configured:
        raise UnauthorizedError(
            "n8n webhook secret is not configured",
            details={"hint": "Set N8N_WEBHOOK_SECRET"},
        )

    timestamp_raw = request.headers.get(TIMESTAMP_HEADER)
    if cfg.n8n_webhook_require_timestamp:
        validate_webhook_timestamp(
            timestamp_raw,
            max_skew_seconds=cfg.n8n_webhook_max_skew_seconds,
        )

    expected_secret = cfg.n8n_webhook_secret.get_secret_value().strip()  # type: ignore[union-attr]
    header_name = (cfg.n8n_webhook_header or HEADER_NAME).strip() or HEADER_NAME

    provided_secret = (request.headers.get(header_name) or "").strip()
    if not provided_secret:
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            provided_secret = auth[7:].strip()

    if not provided_secret or not constant_time_equals(provided_secret, expected_secret):
        record_security_event(
            session,
            event_type=WEBHOOK_SIGNATURE_INVALID,
            reason="invalid_or_missing_shared_secret",
            correlation_id=request.headers.get("X-Request-ID"),
        )
        raise UnauthorizedError("Invalid n8n webhook credentials")

    if not cfg.n8n_webhook_require_signature:
        return

    signature = (request.headers.get(SIGNATURE_HEADER) or "").strip()
    nonce = (request.headers.get(NONCE_HEADER) or "").strip()
    if not signature or not timestamp_raw:
        record_security_event(
            session,
            event_type=WEBHOOK_SIGNATURE_INVALID,
            reason="missing_signature_or_timestamp",
        )
        raise UnauthorizedError(
            "Missing n8n webhook signature or timestamp",
            details={"headers": [SIGNATURE_HEADER, TIMESTAMP_HEADER]},
        )
    if not nonce:
        record_security_event(
            session,
            event_type=WEBHOOK_REPLAY_REJECTED,
            reason="missing_nonce",
        )
        raise UnauthorizedError(
            "Missing n8n webhook nonce",
            details={"header": NONCE_HEADER},
        )

    body = await request.body()
    expected_sig = sign_n8n_request(
        secret=expected_secret,
        timestamp=str(timestamp_raw).strip(),
        method=request.method,
        path=request.url.path,
        body=body,
    )
    if not constant_time_equals(signature, expected_sig):
        record_security_event(
            session,
            event_type=WEBHOOK_SIGNATURE_INVALID,
            reason="hmac_mismatch",
        )
        raise UnauthorizedError("Invalid n8n webhook signature")

    if session is None:
        return

    existing = session.scalar(
        select(WebhookNonce).where(
            WebhookNonce.source == "n8n",
            WebhookNonce.nonce == nonce[:128],
        )
    )
    if existing is not None:
        record_security_event(
            session,
            event_type=WEBHOOK_REPLAY_REJECTED,
            reason="nonce_reuse",
            details={"nonce_prefix": nonce[:8]},
        )
        raise UnauthorizedError("Webhook replay rejected")

    session.add(
        WebhookNonce(
            source="n8n",
            nonce=nonce[:128],
            signature_prefix=signature[:16],
            expires_at=utc_now()
            + timedelta(seconds=max(cfg.n8n_webhook_max_skew_seconds * 2, 600)),
        )
    )
    session.flush()
