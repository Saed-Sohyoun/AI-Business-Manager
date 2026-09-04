"""Company — durable business entity in company memory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CompanyStatus

if TYPE_CHECKING:
    from app.models.company_audit import CompanyAudit
    from app.models.company_evidence import CompanyEvidence
    from app.models.company_score import CompanyScore
    from app.models.company_source import CompanySource
    from app.models.lead import Lead


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_status", "status"),
        Index("ix_companies_industry", "industry"),
        Index("ix_companies_name", "name"),
        Index("ix_companies_website_domain", "website_domain"),
        UniqueConstraint("website_domain", name="uq_companies_website_domain"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    website_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[CompanyStatus] = mapped_column(
        String(32),
        nullable=False,
        default=CompanyStatus.PROSPECT,
        server_default=CompanyStatus.PROSPECT.value,
    )

    leads: Mapped[list["Lead"]] = relationship(
        "Lead",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sources: Mapped[list["CompanySource"]] = relationship(
        "CompanySource",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    evidence: Mapped[list["CompanyEvidence"]] = relationship(
        "CompanyEvidence",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    scores: Mapped[list["CompanyScore"]] = relationship(
        "CompanyScore",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audits: Mapped[list["CompanyAudit"]] = relationship(
        "CompanyAudit",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r} status={self.status}>"
