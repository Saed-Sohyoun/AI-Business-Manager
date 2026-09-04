"""Follow-up sequence and scheduled follow-up items.

Tracks initial outreach, cadence, replies, and stop reasons without mass-send.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FollowUpItemStatus, FollowUpSequenceStatus, FollowUpStopReason

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.lead import Lead
    from app.models.outreach import Outreach


class FollowUpSequence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One follow-up cadence per lead, started after initial outreach is sent."""

    __tablename__ = "follow_up_sequences"
    __table_args__ = (
        UniqueConstraint("lead_id", name="uq_follow_up_sequences_lead_id"),
        UniqueConstraint("idempotency_key", name="uq_follow_up_sequences_idempotency_key"),
        Index("ix_follow_up_sequences_status", "status"),
        Index("ix_follow_up_sequences_next_follow_up_at", "next_follow_up_at"),
        Index("ix_follow_up_sequences_company_id", "company_id"),
        Index("ix_follow_up_sequences_initial_outreach_id", "initial_outreach_id"),
    )

    lead_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    initial_outreach_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outreaches.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    initial_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    follow_up_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_follow_up_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[FollowUpSequenceStatus] = mapped_column(
        String(32),
        nullable=False,
        default=FollowUpSequenceStatus.ACTIVE,
        server_default=FollowUpSequenceStatus.ACTIVE.value,
    )
    stop_reason: Mapped[FollowUpStopReason] = mapped_column(
        String(32),
        nullable=False,
        default=FollowUpStopReason.NONE,
        server_default=FollowUpStopReason.NONE.value,
    )

    response_received: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_to_followup_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    """0 = replied to initial; 1+ = replied after that follow-up index."""

    meetings_generated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    lead: Mapped["Lead"] = relationship("Lead")
    company: Mapped["Company"] = relationship("Company")
    initial_outreach: Mapped["Outreach"] = relationship("Outreach")
    items: Mapped[list["FollowUpItem"]] = relationship(
        "FollowUpItem",
        back_populates="sequence",
        order_by="FollowUpItem.followup_index",
    )

    def __repr__(self) -> str:
        return (
            f"<FollowUpSequence id={self.id} lead={self.lead_id} "
            f"status={self.status} count={self.follow_up_count}>"
        )


class FollowUpItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single scheduled follow-up within a sequence (max 2 per lead)."""

    __tablename__ = "follow_up_items"
    __table_args__ = (
        UniqueConstraint(
            "sequence_id",
            "followup_index",
            name="uq_follow_up_items_sequence_id_followup_index",
        ),
        UniqueConstraint("idempotency_key", name="uq_follow_up_items_idempotency_key"),
        Index("ix_follow_up_items_status", "status"),
        Index("ix_follow_up_items_scheduled_for", "scheduled_for"),
        Index("ix_follow_up_items_sequence_id", "sequence_id"),
        Index("ix_follow_up_items_outreach_id", "outreach_id"),
    )

    sequence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("follow_up_sequences.id", ondelete="CASCADE"),
        nullable=False,
    )
    followup_index: Mapped[int] = mapped_column(Integer, nullable=False)
    """1-based index (1 = first follow-up, 2 = second)."""

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    outreach_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outreaches.id", ondelete="SET NULL"),
        nullable=True,
    )
    outbound_message_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outbound_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    approval_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )

    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[FollowUpItemStatus] = mapped_column(
        String(32),
        nullable=False,
        default=FollowUpItemStatus.SCHEDULED,
        server_default=FollowUpItemStatus.SCHEDULED.value,
    )
    skip_reason: Mapped[FollowUpStopReason] = mapped_column(
        String(32),
        nullable=False,
        default=FollowUpStopReason.NONE,
        server_default=FollowUpStopReason.NONE.value,
    )

    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    sequence: Mapped["FollowUpSequence"] = relationship(
        "FollowUpSequence",
        back_populates="items",
    )
    outreach: Mapped[Optional["Outreach"]] = relationship("Outreach")

    def __repr__(self) -> str:
        return (
            f"<FollowUpItem id={self.id} seq={self.sequence_id} "
            f"index={self.followup_index} status={self.status}>"
        )
