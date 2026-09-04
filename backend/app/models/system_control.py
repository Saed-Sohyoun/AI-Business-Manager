"""SystemControlState — singleton owner-controlled operational switches."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.system_mode import SystemMode

# Singleton key — always one logical control row
SYSTEM_CONTROL_KEY = "default"


class SystemControlState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "system_control_state"
    __table_args__ = (Index("ix_system_control_state_key", "control_key", unique=True),)

    control_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SYSTEM_CONTROL_KEY,
        server_default=SYSTEM_CONTROL_KEY,
    )
    system_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SystemMode.NORMAL.value,
        server_default=SystemMode.NORMAL.value,
    )
    ai_operations_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    outbound_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    spending_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    browser_automation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    safe_mode_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    safe_mode_entered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_changed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<SystemControlState mode={self.system_mode!r} "
            f"ai={self.ai_operations_enabled} outbound={self.outbound_enabled}>"
        )
