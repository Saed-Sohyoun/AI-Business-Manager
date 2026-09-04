"""Owner account — minimal auth identity for session login."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OwnerAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "owner_accounts"
    __table_args__ = (
        UniqueConstraint("email", name="uq_owner_accounts_email"),
        Index("ix_owner_accounts_email", "email"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="Owner")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<OwnerAccount email={self.email!r} active={self.active}>"
