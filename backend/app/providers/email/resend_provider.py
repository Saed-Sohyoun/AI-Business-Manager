"""Resend adapter implementing EmailProvider.

Uses httpx against the Resend HTTP API. This is the only module that should
know Resend-specific request/response shapes. Business logic must depend on
EmailProvider / EmailService instead.
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from app.config import Settings
from app.providers.email.base import EmailProvider
from app.providers.email.costing import estimate_email_cost
from app.providers.email.exceptions import (
    EmailConfigurationError,
    EmailMalformedResponseError,
    EmailProviderError,
    EmailRateLimitError,
    EmailTimeoutError,
    EmailValidationError,
)
from app.providers.email.recipient import normalize_and_validate_recipient, normalize_from_address
from app.providers.email.safe_logging import log_email_failed, log_email_started, log_email_succeeded
from app.providers.email.types import EmailSendRequest, EmailSendResponse

RESEND_EMAILS_URL = "https://api.resend.com/emails"


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


class ResendEmailProvider(EmailProvider):
    """Resend email adapter with retries, validation, and normalized errors."""

    name = "resend"

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        sleep_fn: Any | None = None,
        api_url: str = RESEND_EMAILS_URL,
    ) -> None:
        self._settings = settings
        self._client = http_client
        self._owns_client = http_client is None
        self._sleep = sleep_fn or time.sleep
        self._api_url = api_url

    def is_configured(self) -> bool:
        return self._settings.resend_configured

    def send(self, request: EmailSendRequest) -> EmailSendResponse:
        if not self.is_configured():
            raise EmailConfigurationError(
                "RESEND_API_KEY is not configured. Set it in the environment to send email.",
                details={"provider": self.name},
            )
        if not self._settings.email_from:
            raise EmailConfigurationError(
                "EMAIL_FROM is not configured.",
                details={"provider": self.name},
            )

        to = normalize_and_validate_recipient(request.to.email, name=request.to.name)
        from_email = normalize_from_address(request.from_email or self._settings.email_from)
        if not request.subject.strip():
            raise EmailValidationError("Subject is required")
        if not request.body_text.strip():
            raise EmailValidationError("Body text is required")

        max_retries = self._settings.resend_max_retries
        timeout = request.timeout_seconds or self._settings.resend_timeout
        attempts = 0
        last_error: Exception | None = None
        client = self._ensure_client(timeout=timeout)

        while attempts <= max_retries:
            attempts += 1
            log_email_started(
                provider=self.name,
                to_email=to.email,
                subject=request.subject,
                attempt=attempts,
            )
            started = time.perf_counter()
            try:
                payload = self._build_payload(
                    to=to.email,
                    to_name=to.name,
                    from_email=from_email,
                    request=request,
                )
                headers = {
                    "Authorization": f"Bearer {self._settings.resend_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": request.idempotency_key,
                }
                response = client.post(self._api_url, json=payload, headers=headers)
                latency_ms = (time.perf_counter() - started) * 1000.0

                if response.status_code == 429:
                    raise EmailRateLimitError(
                        "Resend rate limit exceeded",
                        details={"status_code": 429, "attempt": attempts},
                    )
                if response.status_code >= 500:
                    raise EmailProviderError(
                        "Resend server error",
                        details={"status_code": response.status_code, "attempt": attempts},
                    )
                if response.status_code >= 400:
                    # Non-retryable client errors
                    raise EmailProviderError(
                        "Resend rejected the email request",
                        details={
                            "status_code": response.status_code,
                            "attempt": attempts,
                            "retryable": False,
                        },
                    )

                data = response.json()
                message_id = data.get("id")
                if not message_id or not isinstance(message_id, str):
                    raise EmailMalformedResponseError(
                        "Resend response missing message id",
                        details={"body_keys": list(data.keys()) if isinstance(data, dict) else []},
                    )

                cost = estimate_email_cost(self._settings.resend_cost_per_email)
                result = EmailSendResponse(
                    provider=self.name,
                    provider_message_id=message_id,
                    delivery_status="accepted",
                    estimated_cost=cost,
                    latency_ms=latency_ms,
                    attempts=attempts,
                    to_email=to.email,
                    subject=request.subject,
                    metadata={"idempotency_key": request.idempotency_key},
                )
                log_email_succeeded(
                    provider=self.name,
                    to_email=to.email,
                    message_id=message_id,
                    latency_ms=latency_ms,
                    attempts=attempts,
                    estimated_cost=cost,
                )
                return result

            except EmailRateLimitError as exc:
                last_error = exc
                log_email_failed(
                    provider=self.name,
                    to_email=to.email,
                    attempt=attempts,
                    error_code=exc.code,
                    error_type=type(exc).__name__,
                )
                if attempts <= max_retries:
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise
            except EmailProviderError as exc:
                last_error = exc
                log_email_failed(
                    provider=self.name,
                    to_email=to.email,
                    attempt=attempts,
                    error_code=exc.code,
                    error_type=type(exc).__name__,
                )
                retryable = bool((exc.details or {}).get("retryable", True))
                status = (exc.details or {}).get("status_code")
                if status and int(status) < 500 and int(status) != 429:
                    raise
                if retryable and attempts <= max_retries:
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise
            except httpx.TimeoutException as exc:
                last_error = EmailTimeoutError(
                    "Resend request timed out",
                    details={"attempt": attempts},
                )
                log_email_failed(
                    provider=self.name,
                    to_email=to.email,
                    attempt=attempts,
                    error_code="email_timeout",
                    error_type="TimeoutException",
                )
                if attempts <= max_retries:
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = EmailProviderError(
                    f"Resend HTTP error: {type(exc).__name__}",
                    details={"attempt": attempts},
                )
                log_email_failed(
                    provider=self.name,
                    to_email=to.email,
                    attempt=attempts,
                    error_code="email_provider_error",
                    error_type=type(exc).__name__,
                )
                if attempts <= max_retries:
                    self._sleep(_retry_after_seconds(exc, attempts))
                    continue
                raise last_error from exc
            except EmailMalformedResponseError:
                raise
            except EmailValidationError:
                raise
            except EmailConfigurationError:
                raise

        if last_error:
            raise last_error
        raise EmailProviderError("Email send failed without specific error")

    def _build_payload(
        self,
        *,
        to: str,
        to_name: str | None,
        from_email: str,
        request: EmailSendRequest,
    ) -> dict[str, Any]:
        to_value = f"{to_name} <{to}>" if to_name else to
        payload: dict[str, Any] = {
            "from": from_email,
            "to": [to_value],
            "subject": request.subject,
            "text": request.body_text,
        }
        if request.body_html:
            payload["html"] = request.body_html
        if request.reply_to:
            payload["reply_to"] = request.reply_to
        return payload

    def _ensure_client(self, *, timeout: float) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(timeout=timeout)
        self._owns_client = True
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None
