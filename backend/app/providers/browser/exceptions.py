"""Browser provider exceptions."""

from __future__ import annotations

from typing import Any

from app.exceptions import AppError


class BrowserError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "browser_error",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class BrowserConfigurationError(BrowserError):
    def __init__(
        self,
        message: str = "Browser provider is not available",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="browser_configuration_error",
            status_code=503,
            details=details,
        )


class BrowserUnsafeURLError(BrowserError):
    def __init__(
        self,
        message: str = "URL is not allowed for browser navigation",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="browser_unsafe_url",
            status_code=400,
            details=details,
        )


class BrowserTimeoutError(BrowserError):
    def __init__(
        self,
        message: str = "Browser operation timed out",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="browser_timeout",
            status_code=504,
            details=details,
        )


class BrowserNavigationError(BrowserError):
    def __init__(
        self,
        message: str = "Browser navigation failed",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="browser_navigation_error",
            status_code=502,
            details=details,
        )


class BrowserPageTooLargeError(BrowserError):
    def __init__(
        self,
        message: str = "Page exceeds maximum allowed size",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="browser_page_too_large",
            status_code=413,
            details=details,
        )
