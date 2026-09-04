"""Pilot budget threshold warnings — OwnerAlert at 70% / 90%, hard stop at 100%."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.system_mode import AlertPriority
from app.owner.alerts import OwnerAlertService
from app.pilot.config import PilotModeConfig


def utc_day_key() -> str:
    from app.models.base import utc_now

    return utc_now().strftime("%Y-%m-%d")


def emit_budget_threshold_alerts(
    session: Session,
    *,
    spent: Decimal,
    limit: Decimal,
    currency: str,
    ratio: Decimal,
    pilot: PilotModeConfig,
    commit: bool = False,
) -> list[str]:
    """Upsert deduped OwnerAlerts for warning / urgent budget thresholds.

    Returns list of levels emitted: ``warning``, ``urgent``.
    Hard stop at 100% remains the caller's assert_daily_budget / BudgetGuard.
    """
    if limit <= 0:
        return []

    emitted: list[str] = []
    day = utc_day_key()
    alerts = OwnerAlertService(session)
    pct = (ratio * 100).quantize(Decimal("0.1"))
    body_base = f"Daily pilot spend {spent} / {limit} {currency} ({pct}%)"

    if ratio >= pilot.budget_urgent_ratio:
        alerts.upsert_alert(
            dedupe_key=f"pilot-budget-urgent-{day}",
            title="Pilot budget nearly exhausted",
            body=f"{body_base}. Approaching hard daily stop.",
            priority=AlertPriority.URGENT,
            source="budget_guard",
            details={
                "spent": str(spent),
                "limit": str(limit),
                "ratio": str(ratio),
                "threshold": str(pilot.budget_urgent_ratio),
            },
            commit=False,
        )
        emitted.append("urgent")

    if ratio >= pilot.budget_warning_ratio:
        # INFO at warning floor; IMPORTANT once past midpoint toward urgent
        mid = (pilot.budget_warning_ratio + pilot.budget_urgent_ratio) / 2
        priority = AlertPriority.IMPORTANT if ratio >= mid else AlertPriority.INFO
        alerts.upsert_alert(
            dedupe_key=f"pilot-budget-warning-{day}",
            title="Pilot budget warning",
            body=f"{body_base}. Consider slowing spend.",
            priority=priority,
            source="budget_guard",
            details={
                "spent": str(spent),
                "limit": str(limit),
                "ratio": str(ratio),
                "threshold": str(pilot.budget_warning_ratio),
            },
            commit=False,
        )
        emitted.append("warning")

    if emitted and commit:
        session.commit()
    elif emitted:
        session.flush()
    return emitted
