"""ManagerRun — top-level goal orchestration session."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import ManagerRunStatus

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.manager_decision import ManagerDecision
    from app.models.manager_task import ManagerTask


class ManagerRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "manager_runs"
    __table_args__ = (
        Index("ix_manager_runs_status", "status"),
        Index("ix_manager_runs_started_at", "started_at"),
        Index("ix_manager_runs_agent_run_id", "agent_run_id"),
    )

    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ManagerRunStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ManagerRunStatus.PENDING,
        server_default=ManagerRunStatus.PENDING.value,
    )
    phase: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="goal",
        server_default="goal",
    )
    plan_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stop_reason: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    target_qualified_leads: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    measured_qualified_leads: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    tasks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tasks_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    business_state: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    agent_run: Mapped[Optional["AgentRun"]] = relationship("AgentRun")
    tasks: Mapped[list["ManagerTask"]] = relationship(
        "ManagerTask",
        back_populates="manager_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ManagerTask.sequence",
    )
    decisions: Mapped[list["ManagerDecision"]] = relationship(
        "ManagerDecision",
        back_populates="manager_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ManagerDecision.created_at",
    )

    def __repr__(self) -> str:
        return f"<ManagerRun id={self.id} status={self.status} goal={self.goal[:40]!r}>"
