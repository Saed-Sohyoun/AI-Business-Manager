"""CompanyEvidence — field-level research evidence (never invented facts)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.company import Company


class CompanyEvidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "company_evidence"
    __table_args__ = (
        Index("ix_company_evidence_company_id", "company_id"),
        Index("ix_company_evidence_agent_run_id", "agent_run_id"),
        Index("ix_company_evidence_field_name", "field_name"),
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
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    field_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # verified | unverified | unknown
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="search")

    company: Mapped["Company"] = relationship("Company", back_populates="evidence")
    agent_run: Mapped[Optional["AgentRun"]] = relationship("AgentRun")

    def __repr__(self) -> str:
        return (
            f"<CompanyEvidence id={self.id} field={self.field_name!r} "
            f"status={self.verification_status}>"
        )
