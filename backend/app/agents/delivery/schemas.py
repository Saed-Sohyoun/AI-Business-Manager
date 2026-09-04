"""Delivery agent schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    depends_on: list[str] = Field(default_factory=list)
    is_sensitive: bool = False
    sort_order: int = 0


class DeliveryRequest(BaseModel):
    """Start delivery from a lead: convert → customer → project → default tasks."""

    model_config = ConfigDict(extra="forbid")

    lead_id: UUID
    project_name: str | None = Field(default=None, max_length=255)
    project_description: str | None = Field(default=None, max_length=4000)
    tasks: list[TaskSpec] | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    task_key: str
    title: str
    status: str
    depends_on: list[str] = Field(default_factory=list)
    is_sensitive: bool = False
    verified: bool = False
    approval_id: UUID | None = None


class DeliverableView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    deliverable_type: str
    status: str
    verified: bool
    task_id: UUID | None = None


class ProjectProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    status: str
    progress_percent: int
    total_tasks: int
    completed_tasks: int
    verified_tasks: int
    blocked_tasks: int
    pending_tasks: int
    deliverable_count: int
    verified: bool
    completed_at: datetime | None = None


class DeliveryRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    status: Literal["succeeded", "failed", "partial"]
    customer_id: UUID | None = None
    project_id: UUID | None = None
    tasks: list[TaskView] = Field(default_factory=list)
    progress: ProjectProgress | None = None
    estimated_cost: Decimal = Decimal("0")
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
