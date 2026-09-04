"""Owner command / execution schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OwnerAPIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindOpportunitiesRequest(OwnerAPIModel):
    niche: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    desired_count: int = Field(default=5, ge=1, le=20)
    goal_id: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)


class FindOpportunitiesResponse(OwnerAPIModel):
    execution_id: UUID
    status: str
    message: str


class ExecutionView(OwnerAPIModel):
    id: UUID
    title: str
    purpose: str
    state: str
    started_at: datetime
    completed_at: datetime | None = None
    progress: int = 0
    completed_steps: int = 0
    total_steps: int = 0
    current_activity: str | None = None
    result_summary: str | None = None
    needs_attention: bool = False
    failure_message: str | None = None
    command_type: str | None = None
    advanced_details: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(OwnerAPIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(OwnerAPIModel):
    email: str
    display_name: str
    csrf_token: str
    auth_method: str = "session"


class SessionMeView(OwnerAPIModel):
    email: str
    display_name: str
    auth_method: str
    csrf_token: str | None = None
    production_locked: bool = True


class GenerateReportRequest(OwnerAPIModel):
    period_type: str = Field(default="daily", max_length=16)
    idempotency_key: str = Field(min_length=8, max_length=128)
