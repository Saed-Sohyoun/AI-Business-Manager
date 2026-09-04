"""Follow-up schemas and metric snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FollowUpMetricsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_sent: int = 0
    responses: int = 0
    response_rate: float = 0.0
    followups_sent: int = 0
    followup_responses: int = 0
    follow_up_response_rate: float = 0.0
    meetings_generated: int = 0


class FollowUpProcessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: UUID
    item_id: UUID | None = None
    action: Literal[
        "drafted_pending_approval",
        "skipped_stopped",
        "skipped_duplicate",
        "skipped_not_due",
        "max_reached",
        "approval_missing_stopped",
    ]
    stop_reason: str | None = None
    approval_id: UUID | None = None
    outreach_id: UUID | None = None
    logs: list[str] = Field(default_factory=list)


class FollowUpSequenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    lead_id: UUID
    company_id: UUID
    initial_outreach_id: UUID
    initial_sent_at: datetime
    follow_up_count: int
    next_follow_up_at: datetime | None
    status: str
    stop_reason: str
    response_received: bool
    response_at: datetime | None = None
    meetings_generated: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
