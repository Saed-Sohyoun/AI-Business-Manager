"""CompanyScore — deterministic, explainable lead score snapshot."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import ScoreBand

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyScore(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "company_scores"
    __table_args__ = (
        Index("ix_company_scores_company_id", "company_id"),
        Index("ix_company_scores_scored_at", "scored_at"),
        Index("ix_company_scores_band", "band"),
        Index("ix_company_scores_version", "scoring_version"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[ScoreBand] = mapped_column(String(32), nullable=False)

    website_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    online_presence: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_capture_process: Mapped[int] = mapped_column(Integer, nullable=False)
    automation_potential: Mapped[int] = mapped_column(Integer, nullable=False)
    commercial_potential: Mapped[int] = mapped_column(Integer, nullable=False)

    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="scores")

    def __repr__(self) -> str:
        return (
            f"<CompanyScore id={self.id} company_id={self.company_id} "
            f"total={self.total_score} band={self.band}>"
        )
