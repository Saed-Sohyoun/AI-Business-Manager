"""Wave 1 — n8n HMAC signature + replay protection."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, clear_settings_cache
from app.database import get_engine, reset_db_state
from app.main import create_app
from app.models import Base
from app.orchestration.auth import sign_n8n_request
from app.security.rate_limit import http_rate_limiter

SECRET = "hmac-test-secret"


def _app():
    http_rate_limiter.reset()
    clear_settings_cache()
    reset_db_state()
    cfg = Settings(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        n8n_webhook_secret=SecretStr(SECRET),
        n8n_webhook_require_timestamp=True,
        n8n_webhook_require_signature=True,
        n8n_webhook_max_skew_seconds=300,
        n8n_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
        health_rate_limit_per_minute=10_000,
    )
    application = create_app(cfg)
    Base.metadata.create_all(bind=get_engine())
    return application


def _headers(body: bytes, *, path: str, nonce: str | None = None) -> dict[str, str]:
    ts = str(int(time.time()))
    nonce = nonce or uuid4().hex
    sig = sign_n8n_request(
        secret=SECRET,
        timestamp=ts,
        method="POST",
        path=path,
        body=body,
    )
    return {
        "X-N8N-Webhook-Secret": SECRET,
        "X-N8N-Timestamp": ts,
        "X-N8N-Signature": sig,
        "X-N8N-Nonce": nonce,
        "Content-Type": "application/json",
    }


def test_valid_signed_webhook_accepted():
    path = "/api/v1/n8n/webhooks/daily-cycle"
    body = b'{"idempotency_key":"sig-ok-1"}'
    with TestClient(_app()) as client:
        resp = client.post(path, content=body, headers=_headers(body, path=path))
    assert resp.status_code in {200, 502, 504}  # handler may fail soft; auth must pass
    # Auth failure would be 401
    assert resp.status_code != 401
    reset_db_state()
    clear_settings_cache()
    http_rate_limiter.reset()


def test_invalid_signature_rejected():
    path = "/api/v1/n8n/webhooks/daily-cycle"
    body = b'{"idempotency_key":"sig-bad-1"}'
    headers = _headers(body, path=path)
    headers["X-N8N-Signature"] = "sha256=" + ("0" * 64)
    with TestClient(_app()) as client:
        resp = client.post(path, content=body, headers=headers)
    assert resp.status_code == 401
    reset_db_state()
    clear_settings_cache()
    http_rate_limiter.reset()


def test_modified_body_rejected():
    path = "/api/v1/n8n/webhooks/daily-cycle"
    body = b'{"idempotency_key":"sig-body-1"}'
    headers = _headers(body, path=path)
    with TestClient(_app()) as client:
        resp = client.post(
            path,
            content=b'{"idempotency_key":"tampered"}',
            headers=headers,
        )
    assert resp.status_code == 401
    reset_db_state()
    clear_settings_cache()
    http_rate_limiter.reset()


def test_replay_nonce_rejected():
    path = "/api/v1/n8n/webhooks/daily-cycle"
    body = b'{"idempotency_key":"sig-replay-1"}'
    nonce = uuid4().hex
    headers = _headers(body, path=path, nonce=nonce)
    with TestClient(_app()) as client:
        first = client.post(path, content=body, headers=headers)
        assert first.status_code != 401
        # Same nonce + new signature still replay
        headers2 = _headers(body, path=path, nonce=nonce)
        second = client.post(path, content=body, headers=headers2)
    assert second.status_code == 401
    reset_db_state()
    clear_settings_cache()
    http_rate_limiter.reset()
