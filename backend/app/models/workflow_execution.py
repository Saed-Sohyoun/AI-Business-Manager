"""WorkflowExecution — durable ledger for n8n-triggered orchestration runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import WorkflowExecutionStatus, WorkflowName


class WorkflowExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_executions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_name",
            "idempotency_key",
            name="uq_workflow_executions_name_idempotency",
        ),
        Index("ix_workflow_executions_workflow_name", "workflow_name"),
        Index("ix_workflow_executions_status", "status"),
        Index("ix_workflow_executions_started_at", "started_at"),
        Index("ix_workflow_executions_idempotency_key", "idempotency_key"),
    )

    workflow_name: Mapped[WorkflowName] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[WorkflowExecutionStatus] = mapped_column(
        String(32),
        nullable=False,
        default=WorkflowExecutionStatus.RECEIVED,
        server_default=WorkflowExecutionStatus.RECEIVED.value,
    )
    trigger_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="n8n",
        server_default="n8n",
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=120.0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowExecution id={self.id} workflow={self.workflow_name} "
            f"status={self.status} attempt={self.attempt}>"
        )
