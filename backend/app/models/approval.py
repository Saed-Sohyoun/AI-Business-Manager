"""Approval — human-in-the-loop gate for YELLOW/RED actions.

Resolved approvals are treated as immutable for status, risk, payload, and
action identity. Audit history lives in ApprovalEvent rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import ApprovalStatus, RiskLevel

if TYPE_CHECKING:
    from app.models.approval_event import ApprovalEvent


TERMINAL_APPROVAL_STATUSES = frozenset(
    {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.CANCELLED,
    }
)


class Approval(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_status", "status"),
        Index("ix_approvals_risk_level", "risk_level"),
        Index("ix_approvals_action_type", "action_type"),
        Index("ix_approvals_requested_at", "requested_at"),
        Index("ix_approvals_fingerprint", "fingerprint"),
        Index("ix_approvals_expires_at", "expires_at"),
    )

    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        String(32),
        nullable=False,
        default=RiskLevel.YELLOW,
        server_default=RiskLevel.YELLOW.value,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ApprovalStatus.PENDING,
        server_default=ApprovalStatus.PENDING.value,
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
    )
    action_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="system",
        server_default="system",
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_run_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    manager_task_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    events: Mapped[list["ApprovalEvent"]] = relationship(
        "ApprovalEvent",
        back_populates="approval",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ApprovalEvent.created_at",
    )

    @property
    def is_terminal(self) -> bool:
        status = self.status if isinstance(self.status, ApprovalStatus) else ApprovalStatus(self.status)
        return status in TERMINAL_APPROVAL_STATUSES

    def __repr__(self) -> str:
        return (
            f"<Approval id={self.id} action={self.action_type!r} "
            f"risk={self.risk_level} status={self.status}>"
        )
