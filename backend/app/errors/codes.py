"""Centralized error codes for owner/API responses."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    AGENT_SCOPE_VIOLATION = "AGENT_SCOPE_VIOLATION"
    POLICY_DENIED = "POLICY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_PAYLOAD_MISMATCH = "APPROVAL_PAYLOAD_MISMATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SYSTEM_PAUSED = "SYSTEM_PAUSED"
    SAFE_MODE_ACTIVE = "SAFE_MODE_ACTIVE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    DUPLICATE_OPERATION = "DUPLICATE_OPERATION"
    STATE_TRANSITION_INVALID = "STATE_TRANSITION_INVALID"
    LIMIT_REACHED = "LIMIT_REACHED"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


# Map AppError.code → ErrorCode when possible
APP_CODE_TO_ERROR: dict[str, ErrorCode] = {
    "unauthorized": ErrorCode.AUTH_REQUIRED,
    "forbidden": ErrorCode.FORBIDDEN,
    "validation_error": ErrorCode.VALIDATION_ERROR,
    "not_found": ErrorCode.NOT_FOUND,
    "conflict": ErrorCode.CONFLICT,
    "agent_scope_violation": ErrorCode.AGENT_SCOPE_VIOLATION,
    "approval_payload_mismatch": ErrorCode.APPROVAL_PAYLOAD_MISMATCH,
    "limit_reached": ErrorCode.LIMIT_REACHED,
    "service_unavailable": ErrorCode.PROVIDER_UNAVAILABLE,
    "workflow_timeout": ErrorCode.TIMEOUT,
}
