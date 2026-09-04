"""CompanySource — provenance URLs discovered during research."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.company import Company


class CompanySource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "company_sources"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "normalized_url",
            name="uq_company_sources_company_id_normalized_url",
        ),
        Index("ix_company_sources_company_id", "company_id"),
        Index("ix_company_sources_agent_run_id", "agent_run_id"),
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
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="search")

    company: Mapped["Company"] = relationship("Company", back_populates="sources")
    agent_run: Mapped[Optional["AgentRun"]] = relationship("AgentRun")

    def __repr__(self) -> str:
        return f"<CompanySource id={self.id} url={self.url!r}>"
