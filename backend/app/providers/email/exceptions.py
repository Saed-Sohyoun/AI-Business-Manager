"""Email provider exceptions."""

from __future__ import annotations

from typing import Any

from app.exceptions import AppError


class EmailError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "email_error",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class EmailConfigurationError(EmailError):
    def __init__(
        self,
        message: str = "Email provider is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="email_configuration_error",
            status_code=503,
            details=details,
        )


class EmailValidationError(EmailError):
    def __init__(
        self,
        message: str = "Email validation failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="email_validation_error",
            status_code=422,
            details=details,
        )


class EmailTimeoutError(EmailError):
    def __init__(
        self,
        message: str = "Email provider request timed out",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code="email_timeout", status_code=504, details=details)


class EmailRateLimitError(EmailError):
    def __init__(
        self,
        message: str = "Email provider or local rate limit exceeded",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code="email_rate_limit", status_code=429, details=details)


class EmailProviderError(EmailError):
    def __init__(
        self,
        message: str = "Email provider request failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="email_provider_error",
            status_code=502,
            details=details,
        )


class EmailMalformedResponseError(EmailError):
    def __init__(
        self,
        message: str = "Email provider returned a malformed response",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="email_malformed_response",
            status_code=502,
            details=details,
        )


class EmailIdempotencyError(EmailError):
    def __init__(
        self,
        message: str = "Duplicate outbound email blocked by idempotency",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="email_idempotency_conflict",
            status_code=409,
            details=details,
        )
