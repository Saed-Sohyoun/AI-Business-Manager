"""ManagerTask — delegated work unit with explicit state machine."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ManagerTaskStatus, RiskLevel

if TYPE_CHECKING:
    from app.models.approval import Approval
    from app.models.manager_run import ManagerRun


class ManagerTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "manager_tasks"
    __table_args__ = (
        Index("ix_manager_tasks_manager_run_id", "manager_run_id"),
        Index("ix_manager_tasks_status", "status"),
        Index("ix_manager_tasks_agent_name", "agent_name"),
        UniqueConstraint(
            "manager_run_id",
            "fingerprint",
            name="uq_manager_tasks_run_fingerprint",
        ),
    )

    manager_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("manager_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ManagerTaskStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ManagerTaskStatus.PENDING,
        server_default=ManagerTaskStatus.PENDING.value,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        String(32),
        nullable=False,
        default=RiskLevel.GREEN,
        server_default=RiskLevel.GREEN.value,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    approval_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    manager_run: Mapped["ManagerRun"] = relationship("ManagerRun", back_populates="tasks")
    approval: Mapped[Optional["Approval"]] = relationship("Approval")

    def __repr__(self) -> str:
        return (
            f"<ManagerTask id={self.id} agent={self.agent_name!r} "
            f"type={self.task_type!r} status={self.status}>"
        )
