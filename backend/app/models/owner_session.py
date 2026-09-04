"""Owner session — hashed token stored server-side; cookie holds raw token."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class OwnerSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "owner_sessions"
    __table_args__ = (
        Index("ix_owner_sessions_token_hash", "token_hash", unique=True),
        Index("ix_owner_sessions_owner_id", "owner_id"),
        Index("ix_owner_sessions_expires_at", "expires_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("owner_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @property
    def is_valid(self) -> bool:
        if self.revoked_at is not None:
            return False
        now = utc_now()
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=now.tzinfo)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=expires.tzinfo)
        return now < expires
