"""ApprovalEvent — immutable audit trail entries for approvals."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.approval import Approval


class ApprovalEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "approval_events"
    __table_args__ = (
        Index("ix_approval_events_approval_id", "approval_id"),
        Index("ix_approval_events_event_type", "event_type"),
        Index("ix_approval_events_created_at", "created_at"),
    )

    approval_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    approval: Mapped["Approval"] = relationship("Approval", back_populates="events")

    def __repr__(self) -> str:
        return f"<ApprovalEvent id={self.id} type={self.event_type!r} approval={self.approval_id}>"
