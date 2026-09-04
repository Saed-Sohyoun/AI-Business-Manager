"""Lead — contact associated with a company."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LeadScoreCategory, LeadStatus

if TYPE_CHECKING:
    from app.models.company import Company


class Lead(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_leads_company_id_email"),
        Index("ix_leads_status", "status"),
        Index("ix_leads_score_category", "score_category"),
        Index("ix_leads_email", "email"),
        Index("ix_leads_company_id", "company_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    score_category: Mapped[LeadScoreCategory] = mapped_column(
        String(32),
        nullable=False,
        default=LeadScoreCategory.UNSCORED,
        server_default=LeadScoreCategory.UNSCORED.value,
    )
    status: Mapped[LeadStatus] = mapped_column(
        String(32),
        nullable=False,
        default=LeadStatus.NEW,
        server_default=LeadStatus.NEW.value,
    )
    opted_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    blocked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    replied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_contacted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="leads")

    def __repr__(self) -> str:
        return f"<Lead id={self.id} name={self.name!r} status={self.status}>"
