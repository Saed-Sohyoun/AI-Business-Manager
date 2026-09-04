"""Finance ledger — cost entries, revenue entries, and calculated metrics.

All money fields use Decimal / Numeric. Never float.
AI must never invent these numbers; they come from recorded entries + deterministic math.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import CostCategory, RevenueType


class CostEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single recorded cost with precise Decimal amount."""

    __tablename__ = "cost_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_cost_entries_idempotency_key"),
        Index("ix_cost_entries_category", "category"),
        Index("ix_cost_entries_currency", "currency"),
        Index("ix_cost_entries_occurred_at", "occurred_at"),
        Index("ix_cost_entries_source", "source"),
        Index("ix_cost_entries_transaction_reference", "transaction_reference"),
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    category: Mapped[CostCategory] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<CostEntry id={self.id} category={self.category} "
            f"amount={self.amount} {self.currency}>"
        )


class RevenueEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single recorded revenue event with precise Decimal amount."""

    __tablename__ = "revenue_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_revenue_entries_idempotency_key"),
        Index("ix_revenue_entries_revenue_type", "revenue_type"),
        Index("ix_revenue_entries_currency", "currency"),
        Index("ix_revenue_entries_occurred_at", "occurred_at"),
        Index("ix_revenue_entries_source", "source"),
        Index("ix_revenue_entries_transaction_reference", "transaction_reference"),
        Index("ix_revenue_entries_customer_id", "customer_id"),
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    revenue_type: Mapped[RevenueType] = mapped_column(String(32), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    customer_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<RevenueEntry id={self.id} type={self.revenue_type} "
            f"amount={self.amount} {self.currency}>"
        )


class FinancialMetric(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Deterministic financial snapshot for a period — never AI-fabricated."""

    __tablename__ = "financial_metrics"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_financial_metrics_idempotency_key"),
        Index("ix_financial_metrics_currency", "currency"),
        Index("ix_financial_metrics_period_start", "period_start"),
        Index("ix_financial_metrics_period_end", "period_end"),
        Index("ix_financial_metrics_calculated_at", "calculated_at"),
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="finance_agent")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    total_revenue: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    total_costs: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    gross_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    mrr: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )

    ai_costs: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    search_costs: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    email_costs: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    browser_costs: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    delivery_costs: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    other_operational_costs: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )

    # Optional denominators — must be supplied explicitly; never invented by AI.
    lead_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    qualified_lead_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    customer_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    cost_per_lead: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    cost_per_qualified_lead: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    customer_acquisition_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    delivery_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    roi: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)

    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<FinancialMetric id={self.id} revenue={self.total_revenue} "
            f"costs={self.total_costs} profit={self.gross_profit}>"
        )
