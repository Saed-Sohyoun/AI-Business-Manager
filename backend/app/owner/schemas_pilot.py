"""Owner schemas for Wave 5 readiness and pilot experiment."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.owner.schemas import OwnerAPIModel


class ReadinessCheck(OwnerAPIModel):
    id: str
    label: str
    status: Literal["pass", "fail", "warn"]
    detail: str = ""


class ReadinessView(OwnerAPIModel):
    overall: Literal["READY_FOR_PILOT", "NOT_READY"]
    checks: list[ReadinessCheck] = Field(default_factory=list)
    failing_count: int = 0
    production_locked: bool = True
    # Booleans only — never secrets or key material
    providers: dict[str, bool] = Field(default_factory=dict)


class PilotExperimentCreate(OwnerAPIModel):
    niche: str = Field(min_length=1, max_length=255)
    geography: str = Field(default="", max_length=255)
    language: str = Field(default="en", max_length=32)
    company_count_cap: int = Field(default=20, ge=0, le=20)
    qualification_threshold: int = Field(default=60, ge=0, le=100)
    audit_cap: int = Field(default=10, ge=0, le=10)
    outreach_cap: int = Field(default=5, ge=0, le=5)
    daily_budget: Decimal = Field(default=Decimal("3.00"), ge=0, le=Decimal("3.00"))
    start_at: datetime | None = None
    end_at: datetime | None = None
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)


class PilotExperimentView(OwnerAPIModel):
    id: UUID
    niche: str
    geography: str
    language: str
    company_count_cap: int
    qualification_threshold: int
    audit_cap: int
    outreach_cap: int
    daily_budget: Decimal
    start_at: datetime | None = None
    end_at: datetime | None = None
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    status: str
    owner_approved_niche: bool
    version: int
    created_at: datetime
    updated_at: datetime


class PilotObservabilityStatus(OwnerAPIModel):
    production_locked: bool
    pilot_mode: bool
    companies_today: int
    audits_today: int
    outreach_today: int
    spent_today: str
    daily_budget_limit: str
    max_companies_per_day: int
    max_audits_per_day: int
    max_initial_outreach_per_day: int
    active_experiment: PilotExperimentView | None = None
