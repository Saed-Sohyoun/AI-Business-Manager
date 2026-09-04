"""Phase 16 — Telegram notification infrastructure tests."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.models import NotificationRecord
from app.models.enums import NotificationCategory, NotificationPriority, NotificationStatus
from app.providers.notification.exceptions import (
    NotificationConfigurationError,
    NotificationProviderError,
    NotificationRateLimitError,
)
from app.providers.notification.safe_logging import redact_secrets
from app.providers.notification.telegram_provider import TelegramProvider
from app.providers.notification.types import NotificationSendRequest, NotificationSendResponse
from app.services.notification_service import NotificationService


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        telegram_bot_token=SecretStr("123456:ABC-TEST-TOKEN"),
        telegram_chat_id="999001",
        telegram_timeout=5.0,
        telegram_max_retries=1,
        notification_max_per_hour=5,
        notification_max_info_per_day=2,
        notification_min_priority="important",
    )
    base.update(overrides)
    return Settings(**base)


class _FakeResponse:
    def __init__(self, status_code: int, data: dict | None = None):
        self.status_code = status_code
        self._data = data or {}
        self.headers = {}

    def json(self):
        return self._data


@pytest.fixture()
def notify_env(db_session):
    cfg = _settings()
    provider = MagicMock()
    provider.name = "telegram"
    provider.is_configured.return_value = True
    provider.send.return_value = NotificationSendResponse(
        provider="telegram",
        provider_message_id="42",
        latency_ms=11.0,
        attempts=1,
        priority=NotificationPriority.IMPORTANT,
        category=NotificationCategory.APPROVAL_REQUEST,
    )
    service = NotificationService(provider, session=db_session, settings=cfg)
    return {
        "session": db_session,
        "settings": cfg,
        "provider": provider,
        "service": service,
    }


def test_notification_success(notify_env):
    record = notify_env["service"].notify(
        title="Approval required",
        body="Action: sales.send_outreach needs review",
        priority=NotificationPriority.IMPORTANT,
        category=NotificationCategory.APPROVAL_REQUEST,
        idempotency_key="notify:test:1",
    )
    assert record.status == NotificationStatus.SENT
    assert record.provider_message_id == "42"
    assert record.sent_at is not None
    notify_env["provider"].send.assert_called_once()


def test_notification_provider_failure(notify_env):
    notify_env["provider"].send.side_effect = NotificationProviderError("boom")
    with pytest.raises(NotificationProviderError):
        notify_env["service"].notify(
            title="Critical failure",
            body="Agent crashed",
            priority=NotificationPriority.CRITICAL,
            category=NotificationCategory.CRITICAL_FAILURE,
            idempotency_key="notify:fail:1",
        )
    row = notify_env["session"].scalar(select(NotificationRecord).limit(1))
    assert row is not None
    assert row.status == NotificationStatus.FAILED
    assert "boom" in (row.error_message or "")


def test_duplicate_prevention(notify_env):
    first = notify_env["service"].notify(
        title="Daily CEO report ready",
        body="Report generated",
        priority=NotificationPriority.IMPORTANT,
        category=NotificationCategory.DAILY_CEO_REPORT,
        idempotency_key="notify:report:abc",
    )
    second = notify_env["service"].notify(
        title="Daily CEO report ready",
        body="Report generated again",
        priority=NotificationPriority.IMPORTANT,
        category=NotificationCategory.DAILY_CEO_REPORT,
        idempotency_key="notify:report:abc",
    )
    assert first.id == second.id
    assert notify_env["provider"].send.call_count == 1


def test_rate_limit(notify_env):
    cfg = notify_env["settings"].model_copy(update={"notification_max_per_hour": 2})
    service = NotificationService(
        notify_env["provider"],
        session=notify_env["session"],
        settings=cfg,
    )
    for i in range(2):
        service.notify(
            title=f"Alert {i}",
            body="body",
            priority=NotificationPriority.URGENT,
            category=NotificationCategory.BLOCKED_TASK,
            idempotency_key=f"notify:rate:{i}",
        )
    with pytest.raises(NotificationRateLimitError):
        service.notify(
            title="Alert overflow",
            body="body",
            priority=NotificationPriority.URGENT,
            category=NotificationCategory.BLOCKED_TASK,
            idempotency_key="notify:rate:overflow",
        )
    limited = notify_env["session"].scalar(
        select(NotificationRecord).where(
            NotificationRecord.idempotency_key == "notify:rate:overflow"
        )
    )
    assert limited is not None
    assert limited.status == NotificationStatus.RATE_LIMITED
    assert notify_env["provider"].send.call_count == 2


def test_missing_configuration(db_session):
    cfg = _settings(telegram_bot_token=None, telegram_chat_id=None)
    provider = TelegramProvider(cfg)
    assert provider.is_configured() is False
    service = NotificationService(provider, session=db_session, settings=cfg)
    with pytest.raises(NotificationConfigurationError):
        service.notify(
            title="Hello",
            body="World",
            priority=NotificationPriority.IMPORTANT,
            category=NotificationCategory.OTHER,
            idempotency_key="notify:unconfigured",
        )


def test_try_notify_noop_when_unconfigured(db_session):
    cfg = _settings(telegram_bot_token=None, telegram_chat_id=None)
    service = NotificationService(TelegramProvider(cfg), session=db_session, settings=cfg)
    assert (
        service.try_notify(
            title="Hello",
            body="World",
            priority=NotificationPriority.IMPORTANT,
            category=NotificationCategory.OTHER,
            idempotency_key="notify:try-noop",
        )
        is None
    )


def test_info_below_min_priority_skipped(notify_env):
    record = notify_env["service"].notify(
        title="FYI",
        body="low priority note",
        priority=NotificationPriority.INFO,
        category=NotificationCategory.OTHER,
        idempotency_key="notify:info:1",
    )
    assert record.status == NotificationStatus.SKIPPED
    notify_env["provider"].send.assert_not_called()


def test_telegram_provider_send_and_secret_redaction():
    cfg = _settings()
    client = MagicMock()
    client.post.return_value = _FakeResponse(
        200,
        {"ok": True, "result": {"message_id": 77}},
    )
    provider = TelegramProvider(cfg, http_client=client, sleep_fn=lambda _s: None)
    response = provider.send(
        NotificationSendRequest(
            title="Test",
            body="Hello owner",
            priority=NotificationPriority.IMPORTANT,
            category=NotificationCategory.SECURITY_WARNING,
            idempotency_key="tg-1",
        )
    )
    assert response.provider_message_id == "77"
    called_url = client.post.call_args.args[0]
    assert "ABC-TEST-TOKEN" in called_url
    redacted = redact_secrets(called_url, token="ABC-TEST-TOKEN")
    assert "ABC-TEST-TOKEN" not in redacted
    assert "/bot***/" in redacted


def test_convenience_emitters(notify_env):
    approval_id = uuid4()
    record = notify_env["service"].notify_approval_request(
        approval_id=approval_id,
        action_type="sales.send_outreach",
        risk_level="yellow",
        description="Send outreach",
    )
    assert record is not None
    assert record.category == NotificationCategory.APPROVAL_REQUEST
    assert record.status == NotificationStatus.SENT
    notify_env["session"].commit()
