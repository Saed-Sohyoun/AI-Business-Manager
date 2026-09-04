"""OutboundMessage — durable email send ledger with idempotency."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutboundMessageStatus

if TYPE_CHECKING:
    from app.models.outreach import Outreach


class OutboundMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outbound_messages_idempotency_key"),
        Index("ix_outbound_messages_status", "status"),
        Index("ix_outbound_messages_to_email", "to_email"),
        Index("ix_outbound_messages_outreach_id", "outreach_id"),
        Index("ix_outbound_messages_lead_id", "lead_id"),
        Index("ix_outbound_messages_sent_at", "sent_at"),
        Index("ix_outbound_messages_created_at", "created_at"),
    )

    outreach_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outreaches.id", ondelete="SET NULL"),
        nullable=True,
    )
    lead_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    company_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    approval_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[OutboundMessageStatus] = mapped_column(
        String(32),
        nullable=False,
        default=OutboundMessageStatus.DRAFT,
        server_default=OutboundMessageStatus.DRAFT.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    to_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    from_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="resend")
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_followup: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    followup_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sending_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    outreach: Mapped[Optional["Outreach"]] = relationship("Outreach")

    def __repr__(self) -> str:
        return (
            f"<OutboundMessage id={self.id} status={self.status} "
            f"to={self.to_email!r} idem={self.idempotency_key!r}>"
        )
