"""Owner alert records — deduplicated owner-facing operational alerts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.system_mode import AlertPriority


class OwnerAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "owner_alerts"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_owner_alerts_dedupe_key"),
        Index("ix_owner_alerts_priority", "priority"),
        Index("ix_owner_alerts_acknowledged", "acknowledged"),
        Index("ix_owner_alerts_created_at", "created_at"),
    )

    dedupe_key: Mapped[str] = mapped_column(String(191), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AlertPriority.INFO.value,
        server_default=AlertPriority.INFO.value,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<OwnerAlert priority={self.priority!r} title={self.title!r}>"
