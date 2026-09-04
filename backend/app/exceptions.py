"""Application-specific exceptions and API error contracts."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error with stable API fields."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="not_found", status_code=404, details=details)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="conflict", status_code=409, details=details)


class ValidationAppError(AppError):
    def __init__(self, message: str = "Validation failed", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="validation_error", status_code=422, details=details)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="unauthorized", status_code=401, details=details)


class LimitReachedError(AppError):
    def __init__(
        self,
        message: str = "Pilot limit reached",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code="limit_reached", status_code=403, details=details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="forbidden", status_code=403, details=details)


class ApprovalPayloadMismatchError(ForbiddenError):
    """Approved action no longer matches live payload — require a new approval."""

    def __init__(
        self,
        message: str = (
            "This approval is no longer valid because the action changed. "
            "A new approval is required."
        ),
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        AppError.__init__(
            self,
            message,
            code="approval_payload_mismatch",
            status_code=403,
            details=details,
        )


class AgentScopeViolationError(ForbiddenError):
    """Agent requested an action or tool outside its machine-readable contract."""

    def __init__(
        self,
        message: str = (
            "This work was stopped because the team attempted an action "
            "outside its responsibilities."
        ),
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        AppError.__init__(
            self,
            message,
            code="agent_scope_violation",
            status_code=403,
            details=details,
        )


class ServiceUnavailableError(AppError):
    def __init__(
        self,
        message: str = "Service unavailable",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code="service_unavailable", status_code=503, details=details)


class WorkflowTimeoutError(AppError):
    def __init__(
        self,
        message: str = "Workflow execution timed out",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code="workflow_timeout", status_code=504, details=details)
