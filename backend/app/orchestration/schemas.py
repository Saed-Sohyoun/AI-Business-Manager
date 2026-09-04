"""Schemas for n8n webhook orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import WorkflowExecutionStatus, WorkflowName


class WorkflowTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=128)
    timeout_seconds: float | None = Field(default=None, ge=5.0, le=600.0)
    correlation_id: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key")
    @classmethod
    def strip_idempotency_key(cls, value: str) -> str:
        key = value.strip()
        if not key:
            raise ValueError("idempotency_key must not be blank")
        return key

    @field_validator("correlation_id")
    @classmethod
    def strip_correlation_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class WorkflowExecutionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    workflow_name: WorkflowName
    idempotency_key: str
    status: WorkflowExecutionStatus
    attempt: int
    timeout_seconds: float
    trigger_source: str
    started_at: datetime
    finished_at: datetime | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    agent_run_id: UUID | None = None
    correlation_id: str | None = None
    idempotent_replay: bool = False
    retryable: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowTriggerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution: WorkflowExecutionView
