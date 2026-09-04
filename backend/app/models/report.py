"""Stored CEO / business reports generated from real database data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import BusinessReportStatus, ReportPeriodType


class BusinessReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted report with FACT / INTERPRETATION / RECOMMENDATION sections."""

    __tablename__ = "business_reports"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_business_reports_idempotency_key"),
        Index("ix_business_reports_period_type", "period_type"),
        Index("ix_business_reports_period_start", "period_start"),
        Index("ix_business_reports_period_end", "period_end"),
        Index("ix_business_reports_status", "status"),
        Index("ix_business_reports_generated_at", "generated_at"),
    )

    period_type: Mapped[ReportPeriodType] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[BusinessReportStatus] = mapped_column(
        String(32),
        nullable=False,
        default=BusinessReportStatus.GENERATED,
        server_default=BusinessReportStatus.GENERATED.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="report_agent")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    # Ordered list of section dicts (title, statements with kind).
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Raw countable facts used to build the report (auditability).
    facts_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<BusinessReport id={self.id} period={self.period_type} "
            f"title={self.title!r}>"
        )
