"""WebhookNonce — replay protection for signed n8n webhooks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class WebhookNonce(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "webhook_nonces"
    __table_args__ = (
        UniqueConstraint("source", "nonce", name="uq_webhook_nonces_source_nonce"),
        Index("ix_webhook_nonces_expires_at", "expires_at"),
    )

    source: Mapped[str] = mapped_column(String(64), nullable=False, default="n8n")
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    signature_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<WebhookNonce source={self.source!r} nonce={self.nonce[:8]!r}...>"
