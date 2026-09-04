"""FinanceAgent schemas — amounts are Decimal strings or Decimal, never float."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.finance.calculations import as_decimal, normalize_currency
from app.models.enums import CostCategory, RevenueType


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("Floating-point values are not allowed for financial amounts")
    return value


class CostRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal
    currency: str = "USD"
    category: CostCategory
    source: str = Field(min_length=1, max_length=128)
    transaction_reference: str | None = Field(default=None, max_length=128)
    occurred_at: datetime | None = None
    description: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount", mode="before")
    @classmethod
    def amount_no_float(cls, value: object) -> object:
        return _reject_float(value)

    @field_validator("amount")
    @classmethod
    def amount_decimal(cls, value: Decimal) -> Decimal:
        return as_decimal(value)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class RevenueRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal
    currency: str = "USD"
    revenue_type: RevenueType = RevenueType.ONE_TIME
    is_recurring: bool = False
    source: str = Field(min_length=1, max_length=128)
    transaction_reference: str | None = Field(default=None, max_length=128)
    customer_id: UUID | None = None
    occurred_at: datetime | None = None
    description: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount", mode="before")
    @classmethod
    def amount_no_float(cls, value: object) -> object:
        return _reject_float(value)

    @field_validator("amount")
    @classmethod
    def amount_decimal(cls, value: Decimal) -> Decimal:
        return as_decimal(value)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class FinanceCalculateRequest(BaseModel):
    """Calculate metrics from recorded ledger entries for a period.

    Denominator counts must be provided explicitly — never invented.
    """

    model_config = ConfigDict(extra="forbid")

    period_start: datetime
    period_end: datetime
    currency: str = "USD"
    lead_count: int = Field(default=0, ge=0)
    qualified_lead_count: int = Field(default=0, ge=0)
    customer_count: int = Field(default=0, ge=0)
    idempotency_key: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class CostBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai: Decimal = Decimal("0")
    search: Decimal = Decimal("0")
    email: Decimal = Decimal("0")
    browser: Decimal = Decimal("0")
    delivery: Decimal = Decimal("0")
    other_operational: Decimal = Decimal("0")


class FinancialMetricView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    period_start: datetime
    period_end: datetime
    currency: str
    total_revenue: Decimal
    total_costs: Decimal
    gross_profit: Decimal
    mrr: Decimal
    cost_breakdown: CostBreakdown
    cost_per_lead: Decimal | None
    cost_per_qualified_lead: Decimal | None
    customer_acquisition_cost: Decimal | None
    delivery_cost: Decimal
    roi: Decimal | None
    lead_count: int
    qualified_lead_count: int
    customer_count: int
    calculated_at: datetime
    source: str


class FinanceRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    status: Literal["succeeded", "failed"]
    metric: FinancialMetricView | None = None
    estimated_cost: Decimal = Decimal("0")
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
