"""PilotExperiment — owner-scoped controlled pilot run definition."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PilotExperiment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Minimal experiment envelope for Wave 5 pilot readiness."""

    __tablename__ = "pilot_experiments"
    __table_args__ = (
        Index("ix_pilot_experiments_status", "status"),
        Index("ix_pilot_experiments_start_at", "start_at"),
    )

    niche: Mapped[str] = mapped_column(String(255), nullable=False)
    geography: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="en")
    company_count_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    qualification_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    audit_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    outreach_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    daily_budget: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("3.00")
    )
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    success_criteria: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default="draft"
    )
    owner_approved_niche: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<PilotExperiment id={self.id} niche={self.niche!r} status={self.status!r}>"
