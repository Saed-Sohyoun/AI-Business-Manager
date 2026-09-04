"""PilotMode configuration snapshot derived from Settings."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings


class PilotModeConfig(BaseModel):
    """Explicit pilot envelope — defaults match Phase 22 product limits."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    operating_mode: str = "pilot"
    currency: str = "EUR"

    max_companies_per_day: int = 20
    max_audits_per_day: int = 10
    max_initial_outreach_per_day: int = 5
    max_followups_per_lead: int = 2
    max_daily_spending: Decimal = Field(default=Decimal("3.00"))
    max_single_expense: Decimal = Field(default=Decimal("20.00"))
    budget_warning_ratio: Decimal = Field(default=Decimal("0.70"))
    budget_urgent_ratio: Decimal = Field(default=Decimal("0.90"))

    # Actions that always require human approval in pilot (and policy)
    approval_required_actions: tuple[str, ...] = (
        "sales.first_outreach",
        "sales.send_outreach",
        "commerce.purchase",
        "commerce.discount",
        "legal.contract",
        "strategy.major_change",
    )


def pilot_mode_from_settings(settings: Settings) -> PilotModeConfig:
    """Build PilotModeConfig from centralized Settings (single source of truth)."""
    return PilotModeConfig(
        enabled=settings.is_pilot_mode,
        operating_mode=settings.operating_mode,
        currency=settings.pilot_currency,
        max_companies_per_day=settings.max_companies_per_day,
        max_audits_per_day=settings.max_audits_per_day,
        max_initial_outreach_per_day=settings.max_initial_outreach_per_day,
        max_followups_per_lead=settings.max_followups,
        max_daily_spending=settings.daily_budget_limit,
        max_single_expense=settings.max_single_expense,
        budget_warning_ratio=settings.budget_warning_ratio,
        budget_urgent_ratio=settings.budget_urgent_ratio,
    )
