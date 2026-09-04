"""Typed execution context for governed operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import utc_now


class ExecutionContext(BaseModel):
    """Carries identity for Tool Gateway / contract / approval checks."""

    model_config = ConfigDict(extra="forbid")

    execution_id: UUID = Field(default_factory=uuid4)
    correlation_id: str | None = None
    agent_id: str = Field(min_length=1, max_length=64)
    task_id: str | None = None
    goal_id: str | None = None
    policy_version: str | None = None
    contract_version: str | None = None
    request_source: str = "internal"
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "execution_id": str(self.execution_id),
            "correlation_id": self.correlation_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "goal_id": self.goal_id,
            "policy_version": self.policy_version,
            "contract_version": self.contract_version,
            "request_source": self.request_source,
        }
