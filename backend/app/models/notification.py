"""Notification ledger — durable send records with idempotency."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import NotificationCategory, NotificationPriority, NotificationStatus


class NotificationRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notification_records"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_records_idempotency_key"),
        Index("ix_notification_records_status", "status"),
        Index("ix_notification_records_priority", "priority"),
        Index("ix_notification_records_category", "category"),
        Index("ix_notification_records_created_at", "created_at"),
        Index("ix_notification_records_sent_at", "sent_at"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    priority: Mapped[NotificationPriority] = mapped_column(String(16), nullable=False)
    category: Mapped[NotificationCategory] = mapped_column(String(64), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        String(32),
        nullable=False,
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="telegram")
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationRecord id={self.id} priority={self.priority} "
            f"category={self.category} status={self.status}>"
        )
