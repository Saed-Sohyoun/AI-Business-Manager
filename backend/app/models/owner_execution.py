"""OwnerExecution — durable ledger for owner-initiated business commands."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.owner_execution_enums import OwnerCommandType, OwnerExecutionState


class OwnerExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "owner_executions"
    __table_args__ = (
        UniqueConstraint("command_type", "idempotency_key", name="uq_owner_executions_cmd_idem"),
        Index("ix_owner_executions_status", "status"),
        Index("ix_owner_executions_started_at", "started_at"),
        Index("ix_owner_executions_command_type", "command_type"),
    )

    command_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=OwnerExecutionState.QUEUED.value,
        server_default=OwnerExecutionState.QUEUED.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completed_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_activity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    needs_attention: Mapped[bool] = mapped_column(default=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manager_run_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False, server_default="0")
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<OwnerExecution cmd={self.command_type!r} status={self.status!r}>"
