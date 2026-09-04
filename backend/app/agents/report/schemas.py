"""ReportAgent schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.finance.calculations import normalize_currency
from app.models.enums import ReportPeriodType, ReportStatementKind


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_type: ReportPeriodType = ReportPeriodType.DAILY
    # Optional explicit window; if omitted, derived from period_type + as_of.
    period_start: datetime | None = None
    period_end: datetime | None = None
    as_of: datetime | None = None
    currency: str = "USD"
    idempotency_key: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class ReportStatementView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReportStatementKind
    text: str
    value: str | None = None
    available: bool = True


class ReportSectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    order: int
    statements: list[ReportStatementView] = Field(default_factory=list)


class BusinessReportView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    period_type: ReportPeriodType
    period_start: datetime
    period_end: datetime
    title: str
    currency: str
    sections: list[ReportSectionView]
    facts_snapshot: dict[str, Any]
    generated_at: datetime
    source: str


class ReportRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    status: Literal["succeeded", "failed"]
    report: BusinessReportView | None = None
    estimated_cost: Decimal = Decimal("0")
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
