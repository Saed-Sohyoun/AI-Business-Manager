"""CompanyAudit — versioned digital presence audit stored in company memory."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import AuditPriority, AuditStatus

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.company import Company


class CompanyAudit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "company_audits"
    __table_args__ = (
        Index("ix_company_audits_company_id", "company_id"),
        Index("ix_company_audits_agent_run_id", "agent_run_id"),
        Index("ix_company_audits_priority", "priority"),
        Index("ix_company_audits_status", "status"),
        Index("ix_company_audits_version", "audit_version"),
        Index("ix_company_audits_audited_at", "audited_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    audit_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[AuditStatus] = mapped_column(String(32), nullable=False)
    priority: Mapped[AuditPriority] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0"))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommended_solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estimated_business_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    estimated_business_value_currency: Mapped[Optional[str]] = mapped_column(
        String(8),
        nullable=True,
    )
    estimated_business_value_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    problems: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    opportunities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evidence_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    observations: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_catalog: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

    audited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="audits")
    agent_run: Mapped[Optional["AgentRun"]] = relationship("AgentRun")

    def __repr__(self) -> str:
        return (
            f"<CompanyAudit id={self.id} company_id={self.company_id} "
            f"priority={self.priority} version={self.audit_version}>"
        )
