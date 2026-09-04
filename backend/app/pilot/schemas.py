"""Pilot Mode schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


LimitName = Literal[
    "companies_per_day",
    "audits_per_day",
    "initial_outreach_per_day",
    "followups_per_lead",
    "daily_spending",
    "single_expense",
]


class LimitCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    limit_name: LimitName
    used: int | Decimal
    limit: int | Decimal
    remaining: int | Decimal
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BudgetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spent_today: Decimal
    daily_limit: Decimal
    remaining: Decimal
    currency: str
    warning: bool
    urgent: bool = False
    exhausted: bool
    ratio: Decimal


class GuardDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    action_type: str
    reason: str | None = None
    requires_approval: bool = False
    limit_name: LimitName | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PilotStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pilot_mode: bool
    operating_mode: str
    currency: str
    limits: dict[str, Any]
    usage: dict[str, Any]
    budget: BudgetStatus
    approval_required_actions: list[str]
    production_unlock_required: bool
