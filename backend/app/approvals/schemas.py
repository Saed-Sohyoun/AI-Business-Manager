"""Approval request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApprovalStatus, RiskLevel


GateDecisionLiteral = Literal[
    "allow_auto",
    "require_approval",
    "human_only",
    "deny",
]


class ApprovalRequest(BaseModel):
    """Create a persistent, auditable approval tied to a concrete action."""

    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=4000)
    requested_by: str = Field(min_length=1, max_length=128)
    action_payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel | None = None
    """If omitted, ApprovalPolicy classifies the action."""
    fingerprint: str | None = Field(default=None, min_length=1, max_length=64)
    """Dedup key within pending approvals; computed if omitted."""
    expires_in_seconds: int | None = Field(default=None, ge=60, le=30 * 24 * 3600)
    manager_run_id: UUID | None = None
    manager_task_id: UUID | None = None
    agent_run_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolveApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: UUID
    resolved_by: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=4000)


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: GateDecisionLiteral
    action_type: str
    risk_level: RiskLevel
    reason: str
    approval_id: UUID | None = None
    may_execute: bool = False


class ApprovalView(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    action_type: str
    description: str
    risk_level: RiskLevel
    status: ApprovalStatus
    fingerprint: str
    requested_by: str
    requested_at: datetime
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    expires_at: datetime | None = None
    action_payload: dict[str, Any] = Field(default_factory=dict)
    manager_run_id: UUID | None = None
    manager_task_id: UUID | None = None
    agent_run_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    approval_id: UUID
    event_type: str
    actor: str
    detail: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
