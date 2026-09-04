"""Outreach — drafted sales message stored before any external send."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import OutreachStatus

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.company import Company
    from app.models.company_audit import CompanyAudit
    from app.models.company_score import CompanyScore
    from app.models.lead import Lead


class Outreach(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "outreaches"
    __table_args__ = (
        Index("ix_outreaches_company_id", "company_id"),
        Index("ix_outreaches_lead_id", "lead_id"),
        Index("ix_outreaches_status", "status"),
        Index("ix_outreaches_agent_run_id", "agent_run_id"),
        Index("ix_outreaches_created_at", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_score_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_scores.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_audit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_audits.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[OutreachStatus] = mapped_column(
        String(32),
        nullable=False,
        default=OutreachStatus.DRAFT,
        server_default=OutreachStatus.DRAFT.value,
    )
    outreach_version: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(500), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    recipient_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipient_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    personalization_reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    evidence_used: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evidence_catalog: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    drafted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    company: Mapped["Company"] = relationship("Company")
    lead: Mapped["Lead"] = relationship("Lead")
    company_score: Mapped[Optional["CompanyScore"]] = relationship("CompanyScore")
    company_audit: Mapped[Optional["CompanyAudit"]] = relationship("CompanyAudit")
    agent_run: Mapped[Optional["AgentRun"]] = relationship("AgentRun")

    def __repr__(self) -> str:
        return f"<Outreach id={self.id} status={self.status} subject={self.subject[:40]!r}>"
