"""Telegram Bot API adapter implementing NotificationProvider.

This is the only module that should know Telegram-specific request shapes.
Never log TELEGRAM_BOT_TOKEN.
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from app.config import Settings
from app.providers.notification.base import NotificationProvider
from app.providers.notification.exceptions import (
    NotificationConfigurationError,
    NotificationMalformedResponseError,
    NotificationProviderError,
    NotificationRateLimitError,
    NotificationTimeoutError,
    NotificationValidationError,
)
from app.providers.notification.safe_logging import (
    log_notification_failed,
    log_notification_started,
    log_notification_succeeded,
    redact_secrets,
)
from app.providers.notification.types import NotificationSendRequest, NotificationSendResponse

TELEGRAM_API_BASE = "https://api.telegram.org"


def _retry_after_seconds(exc: BaseException, attempt: int) -> float:
    header_value: str | None = None
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        header_value = headers.get("retry-after") or headers.get("Retry-After")
    if header_value:
        try:
            return max(float(header_value), 0.1)
        except ValueError:
            pass
    base = min(2**attempt, 20)
    return base + random.uniform(0, 0.25)


class TelegramProvider(NotificationProvider):
    """Telegram sendMessage adapter with retries and secret-safe errors."""

    name = "telegram"

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        sleep_fn: Any | None = None,
        api_base: str = TELEGRAM_API_BASE,
    ) -> None:
        self._settings = settings
        self._client = http_client
        self._owns_client = http_client is None
        self._sleep = sleep_fn or time.sleep
        self._api_base = api_base.rstrip("/")

    def is_configured(self) -> bool:
        return self._settings.telegram_configured

    def send(self, request: NotificationSendRequest) -> NotificationSendResponse:
        if not self.is_configured():
            raise NotificationConfigurationError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured to send notifications.",
                details={"provider": self.name},
            )
        token = self._settings.telegram_bot_token.get_secret_value().strip()  # type: ignore[union-attr]
        chat_id = (request.chat_id or self._settings.telegram_chat_id or "").strip()
        if not chat_id:
            raise NotificationConfigurationError(
                "TELEGRAM_CHAT_ID is not configured.",
                details={"provider": self.name},
            )
        if not request.title.strip() or not request.body.strip():
            raise NotificationValidationError("Notification title and body are required")

        text = self._format_message(request)
        max_retries = self._settings.telegram_max_retries
        timeout = request.timeout_seconds or self._settings.telegram_timeout
        attempts = 0
        last_error: Exception | None = None
        client = self._ensure_client(timeout=timeout)
        url = f"{self._api_base}/bot{token}/sendMessage"

        while attempts <= max_retries:
            attempts += 1
            log_notification_started(
                provider=self.name,
                priority=request.priority.value,
                category=request.category.value,
                title_len=len(request.title),
                attempt=attempts,
            )
            started = time.perf_counter()
            try:
                response = client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
                latency_ms = (time.perf_counter() - started) * 1000.0

                if response.status_code == 429:
                    raise NotificationRateLimitError(
                        "Telegram rate limit exceeded",
                        details={"status_code": 429},
                    )
                if response.status_code >= 500:
                    raise NotificationProviderError(
                        "Telegram server error",
                        details={"status_code": response.status_code},
                    )
                if response.status_code >= 400:
                    # Do not include response URL (may contain token in some clients)
                    raise NotificationProviderError(
                        "Telegram rejected the notification",
                        details={"status_code": response.status_code},
                    )

                data = response.json()
                if not isinstance(data, dict) or not data.get("ok"):
                    raise NotificationMalformedResponseError(
                        "Telegram response missing ok=true",
                        details={"keys": list(data.keys()) if isinstance(data, dict) else []},
                    )
                result = data.get("result") or {}
                message_id = str(result.get("message_id") or "")
                if not message_id:
                    raise NotificationMalformedResponseError(
                        "Telegram response missing message_id",
                    )

                log_notification_succeeded(
                    provider=self.name,
                    priority=request.priority.value,
                    category=request.category.value,
                    message_id=message_id,
                    latency_ms=latency_ms,
                    attempts=attempts,
                )
                return NotificationSendResponse(
                    provider=self.name,
                    provider_message_id=message_id,
                    latency_ms=latency_ms,
                    attempts=attempts,
                    priority=request.priority,
                    category=request.category,
                    metadata={"chat_configured": True},
                )
            except (NotificationRateLimitError, NotificationProviderError) as exc:
                last_error = exc
                log_notification_failed(
                    provider=self.name,
                    priority=request.priority.value,
                    category=request.category.value,
                    attempt=attempts,
                    error_code=exc.code,
                    error_type=type(exc).__name__,
                )
                if attempts <= max_retries and isinstance(
                    exc, (NotificationRateLimitError, NotificationProviderError)
                ):
                    if getattr(exc, "details", {}).get("status_code", 0) < 500 and not isinstance(
                        exc, NotificationRateLimitError
                    ):
                        raise
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise
            except httpx.TimeoutException as exc:
                last_error = NotificationTimeoutError(
                    "Telegram request timed out",
                    details={"attempt": attempts},
                )
                log_notification_failed(
                    provider=self.name,
                    priority=request.priority.value,
                    category=request.category.value,
                    attempt=attempts,
                    error_code="notification_timeout",
                    error_type=type(exc).__name__,
                )
                if attempts <= max_retries:
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                safe = redact_secrets(str(exc), token=token)
                last_error = NotificationProviderError(
                    "Telegram HTTP error",
                    details={"error": type(exc).__name__, "detail": safe[:200]},
                )
                log_notification_failed(
                    provider=self.name,
                    priority=request.priority.value,
                    category=request.category.value,
                    attempt=attempts,
                    error_code="notification_provider_error",
                    error_type=type(exc).__name__,
                )
                if attempts <= max_retries:
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise last_error from exc

        assert last_error is not None
        raise last_error

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_client(self, *, timeout: float) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=timeout)
            self._owns_client = True
        return self._client

    def _format_message(self, request: NotificationSendRequest) -> str:
        # Keep messages short to avoid spam feel; never include secrets.
        header = f"[{request.priority.value.upper()}] {request.title}".strip()
        body = request.body.strip()
        text = f"{header}\n\n{body}"
        return text[:4000]
