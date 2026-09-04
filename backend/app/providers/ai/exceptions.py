"""AI provider exceptions — normalized failures for the AI abstraction layer."""

from __future__ import annotations

from typing import Any

from app.exceptions import AppError


class AIError(AppError):
    """Base error for AI provider operations."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ai_error",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class AIConfigurationError(AIError):
    """Raised when AI provider configuration is missing or invalid."""

    def __init__(
        self,
        message: str = "AI provider is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ai_configuration_error",
            status_code=503,
            details=details,
        )


class AITimeoutError(AIError):
    def __init__(
        self,
        message: str = "AI provider request timed out",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ai_timeout",
            status_code=504,
            details=details,
        )


class AIRateLimitError(AIError):
    def __init__(
        self,
        message: str = "AI provider rate limit exceeded",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ai_rate_limit",
            status_code=429,
            details=details,
        )


class AIProviderError(AIError):
    def __init__(
        self,
        message: str = "AI provider request failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ai_provider_error",
            status_code=502,
            details=details,
        )


class AIMalformedResponseError(AIError):
    def __init__(
        self,
        message: str = "AI provider returned a malformed response",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ai_malformed_response",
            status_code=502,
            details=details,
        )
