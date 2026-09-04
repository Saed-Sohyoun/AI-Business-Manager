"""Notification provider exceptions."""

from __future__ import annotations

from typing import Any

from app.exceptions import AppError


class NotificationError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "notification_error",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class NotificationConfigurationError(NotificationError):
    def __init__(
        self,
        message: str = "Notification provider is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_configuration_error",
            status_code=503,
            details=details,
        )


class NotificationValidationError(NotificationError):
    def __init__(
        self,
        message: str = "Notification validation failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_validation_error",
            status_code=422,
            details=details,
        )


class NotificationTimeoutError(NotificationError):
    def __init__(
        self,
        message: str = "Notification provider request timed out",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_timeout",
            status_code=504,
            details=details,
        )


class NotificationRateLimitError(NotificationError):
    def __init__(
        self,
        message: str = "Notification rate limit exceeded",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_rate_limit",
            status_code=429,
            details=details,
        )


class NotificationProviderError(NotificationError):
    def __init__(
        self,
        message: str = "Notification provider request failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_provider_error",
            status_code=502,
            details=details,
        )


class NotificationMalformedResponseError(NotificationError):
    def __init__(
        self,
        message: str = "Notification provider returned a malformed response",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_malformed_response",
            status_code=502,
            details=details,
        )


class NotificationIdempotencyError(NotificationError):
    def __init__(
        self,
        message: str = "Duplicate notification blocked by idempotency",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="notification_idempotency_conflict",
            status_code=409,
            details=details,
        )
