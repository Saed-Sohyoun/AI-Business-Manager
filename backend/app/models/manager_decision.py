"""ManagerDecision — durable record of orchestration decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ManagerDecisionType

if TYPE_CHECKING:
    from app.models.manager_run import ManagerRun
    from app.models.manager_task import ManagerTask


class ManagerDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "manager_decisions"
    __table_args__ = (
        Index("ix_manager_decisions_manager_run_id", "manager_run_id"),
        Index("ix_manager_decisions_decision_type", "decision_type"),
        Index("ix_manager_decisions_created_at", "created_at"),
    )

    manager_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("manager_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("manager_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_type: Mapped[ManagerDecisionType] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")

    manager_run: Mapped["ManagerRun"] = relationship("ManagerRun", back_populates="decisions")
    task: Mapped[Optional["ManagerTask"]] = relationship("ManagerTask", foreign_keys=[task_id])

    def __repr__(self) -> str:
        return (
            f"<ManagerDecision id={self.id} type={self.decision_type} "
            f"phase={self.phase!r} action={self.action!r}>"
        )
