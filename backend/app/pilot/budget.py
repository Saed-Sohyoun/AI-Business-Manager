"""BudgetGuard — pilot spending ceilings and near-exhaustion warnings."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import LimitReachedError
from app.pilot.config import PilotModeConfig, pilot_mode_from_settings
from app.pilot.schemas import BudgetStatus, LimitCheckResult
from app.security import assert_daily_budget, assert_max_single_expense, daily_cost_total
from app.services.notification_service import NotificationService


class BudgetGuard:
    """Enforce MAX_DAILY_SPENDING / MAX_SINGLE_EXPENSE and notify near the edge."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        pilot: PilotModeConfig | None = None,
        notifications: NotificationService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._pilot = pilot or pilot_mode_from_settings(settings)
        self._notifications = notifications

    @property
    def config(self) -> PilotModeConfig:
        return self._pilot

    def status(self) -> BudgetStatus:
        spent = daily_cost_total(self._session)
        limit = self._pilot.max_daily_spending
        remaining = max(Decimal("0"), limit - spent)
        ratio = (spent / limit) if limit > 0 else Decimal("1")
        warning = bool(limit > 0 and ratio >= self._pilot.budget_warning_ratio)
        return BudgetStatus(
            spent_today=spent,
            daily_limit=limit,
            remaining=remaining,
            currency=self._pilot.currency,
            warning=warning,
            exhausted=spent >= limit,
            ratio=ratio.quantize(Decimal("0.0001")),
        )

    def check_single_expense(self, amount: Decimal) -> LimitCheckResult:
        limit = self._pilot.max_single_expense
        allowed = amount <= limit
        return LimitCheckResult(
            allowed=allowed,
            limit_name="single_expense",
            used=amount,
            limit=limit,
            remaining=max(Decimal("0"), limit - amount) if allowed else Decimal("0"),
            reason=None if allowed else "max_single_expense",
        )

    def check_daily_spend(self, *, additional: Decimal = Decimal("0")) -> LimitCheckResult:
        spent = daily_cost_total(self._session)
        limit = self._pilot.max_daily_spending
        projected = spent + additional
        allowed = projected <= limit
        return LimitCheckResult(
            allowed=allowed,
            limit_name="daily_spending",
            used=spent,
            limit=limit,
            remaining=max(Decimal("0"), limit - spent),
            reason=None if allowed else "max_daily_spending",
            details={"additional": str(additional), "projected": str(projected)},
        )

    def assert_expense_allowed(self, amount: Decimal) -> BudgetStatus:
        """Fail closed on expense/budget; notify when approaching the daily ceiling."""
        # Keep security helpers as the authoritative money gate (settings-backed).
        try:
            assert_max_single_expense(amount, self._settings)
            assert_daily_budget(self._session, self._settings, additional=amount)
        except Exception as exc:
            # Normalize to LimitReachedError for pilot stop semantics.
            from app.exceptions import ForbiddenError

            if isinstance(exc, ForbiddenError):
                raise LimitReachedError(exc.message, details=exc.details) from exc
            raise

        status = self.status()
        if status.warning and self._notifications is not None:
            self._notifications.notify_budget_warning(
                message=(
                    f"Pilot budget nearly exhausted: {status.spent_today} / "
                    f"{status.daily_limit} {status.currency} "
                    f"({(status.ratio * 100).quantize(Decimal('0.1'))}%)"
                ),
                reference=f"pilot-budget-{utc_day_key()}",
            )
        return status

    def assert_can_spend(self, amount: Decimal) -> LimitCheckResult:
        single = self.check_single_expense(amount)
        if not single.allowed:
            raise LimitReachedError(
                "Expense exceeds max single-expense pilot limit",
                details=single.model_dump(mode="json"),
            )
        daily = self.check_daily_spend(additional=amount)
        if not daily.allowed:
            if self._notifications is not None:
                self._notifications.notify_budget_warning(
                    message=(
                        f"Daily pilot spending limit reached "
                        f"({daily.used}/{daily.limit} {self._pilot.currency})"
                    ),
                    reference=f"pilot-budget-exhausted-{utc_day_key()}",
                )
            raise LimitReachedError(
                "Daily pilot spending limit reached",
                details=daily.model_dump(mode="json"),
            )
        return daily


def utc_day_key() -> str:
    from app.models.base import utc_now

    return utc_now().strftime("%Y-%m-%d")
