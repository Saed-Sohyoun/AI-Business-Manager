"""SecurityEvent — durable governance / safety audit trail (no secrets)."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SecurityEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_event_type", "event_type"),
        Index("ix_security_events_agent_id", "agent_id"),
        Index("ix_security_events_created_at", "created_at"),
        Index("ix_security_events_execution_id", "execution_id"),
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tool: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    contract_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<SecurityEvent type={self.event_type!r} agent={self.agent_id!r}>"
