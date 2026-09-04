"""Search provider exceptions — normalized failures for web search."""

from __future__ import annotations

from typing import Any

from app.exceptions import AppError


class SearchError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "search_error",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class SearchConfigurationError(SearchError):
    def __init__(
        self,
        message: str = "Search provider is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="search_configuration_error",
            status_code=503,
            details=details,
        )


class SearchTimeoutError(SearchError):
    def __init__(
        self,
        message: str = "Search provider request timed out",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="search_timeout",
            status_code=504,
            details=details,
        )


class SearchRateLimitError(SearchError):
    def __init__(
        self,
        message: str = "Search provider rate limit exceeded",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="search_rate_limit",
            status_code=429,
            details=details,
        )


class SearchProviderError(SearchError):
    def __init__(
        self,
        message: str = "Search provider request failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="search_provider_error",
            status_code=502,
            details=details,
        )


class SearchMalformedResponseError(SearchError):
    def __init__(
        self,
        message: str = "Search provider returned a malformed response",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="search_malformed_response",
            status_code=502,
            details=details,
        )
