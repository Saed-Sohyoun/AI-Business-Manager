"""Shared security helpers — constant-time compare, budgets, owner auth stubs."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import ForbiddenError, UnauthorizedError, ValidationAppError
from app.models import CostEntry
from app.models.base import utc_now

logger = logging.getLogger(__name__)


def constant_time_equals(provided: str, expected: str) -> bool:
    """Length-safe constant-time string compare (never raises on length mismatch)."""
    if not isinstance(provided, str) or not isinstance(expected, str):
        return False
    try:
        return secrets.compare_digest(provided, expected)
    except (TypeError, ValueError):
        # Different lengths: still spend comparable work, then fail closed.
        secrets.compare_digest(expected, expected)
        return False


def assert_max_single_expense(amount: Decimal, settings: Settings) -> None:
    """Reject ledger cost lines above the configured single-expense ceiling."""
    ceiling = settings.max_single_expense
    if amount > ceiling:
        raise ForbiddenError(
            "Cost exceeds max_single_expense safety limit",
            details={
                "amount": str(amount),
                "max_single_expense": str(ceiling),
            },
        )


def daily_cost_total(session: Session, *, as_of: datetime | None = None) -> Decimal:
    """Sum CostEntry amounts for the UTC calendar day (ledger facts only)."""
    now = as_of or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    total = session.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).where(
            CostEntry.occurred_at >= day_start,
            CostEntry.occurred_at < day_end,
        )
    )
    return Decimal(str(total or 0))


def assert_daily_budget(
    session: Session,
    settings: Settings,
    *,
    additional: Decimal = Decimal("0"),
    as_of: datetime | None = None,
) -> None:
    """Fail closed when today's ledger costs (+ optional additional) exceed daily_budget_limit."""
    limit = settings.daily_budget_limit
    spent = daily_cost_total(session, as_of=as_of)
    projected = spent + additional
    if projected > limit:
        raise ForbiddenError(
            "Daily budget limit exceeded",
            details={
                "spent_today": str(spent),
                "additional": str(additional),
                "projected": str(projected),
                "daily_budget_limit": str(limit),
            },
        )


def validate_webhook_timestamp(
    raw: str | None,
    *,
    max_skew_seconds: int,
    now: datetime | None = None,
) -> None:
    """Require a recent Unix epoch timestamp to reduce replay of stolen secrets."""
    if raw is None or not str(raw).strip():
        raise UnauthorizedError(
            "Missing webhook timestamp",
            details={"header": "X-N8N-Timestamp"},
        )
    try:
        ts = int(str(raw).strip())
    except ValueError as exc:
        raise UnauthorizedError("Invalid webhook timestamp") from exc

    clock = now or utc_now()
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    event_time = datetime.fromtimestamp(ts, tz=timezone.utc)
    skew = abs((clock - event_time).total_seconds())
    if skew > max_skew_seconds:
        raise UnauthorizedError(
            "Webhook timestamp outside allowed skew",
            details={"max_skew_seconds": max_skew_seconds, "skew_seconds": int(skew)},
        )


def require_owner_identity(
    *,
    provided_api_key: str | None,
    settings: Settings,
    claimed_resolver: str | None = None,
) -> str:
    """Bind owner actions to OWNER_API_KEY. Never trust free-text resolver alone.

    Phase 20: stub for future approve/dashboard HTTP APIs. Fail closed when
    OWNER_API_KEY is unset in non-test environments that attempt owner routes.
    """
    if not settings.owner_api_key_configured:
        if settings.is_test:
            # Tests may exercise resolver logic without HTTP owner auth.
            raise UnauthorizedError(
                "Owner API key is not configured",
                details={"hint": "Set OWNER_API_KEY for owner HTTP actions"},
            )
        raise UnauthorizedError(
            "Owner API key is not configured",
            details={"hint": "Set OWNER_API_KEY"},
        )

    expected = settings.owner_api_key.get_secret_value().strip()  # type: ignore[union-attr]
    if not provided_api_key or not constant_time_equals(provided_api_key.strip(), expected):
        raise UnauthorizedError("Invalid owner credentials")

    allowed = {
        part.strip().lower()
        for part in settings.approval_authorized_resolvers.split(",")
        if part.strip()
    }
    identity = (claimed_resolver or "owner").strip().lower()
    if identity not in allowed:
        raise ForbiddenError(
            "Resolver identity is not authorized",
            details={"resolved_by": identity},
        )
    return identity


def assert_production_settings(settings: Settings) -> None:
    """Fail fast on unsafe production configuration."""
    if settings.operating_mode == "production" and not settings.allow_production_mode:
        raise ValidationAppError(
            "OPERATING_MODE=production requires ALLOW_PRODUCTION_MODE=true",
            details={"operating_mode": settings.operating_mode},
        )
    if not settings.is_production:
        return
    if settings.app_debug:
        raise ValidationAppError(
            "APP_DEBUG must be false in production",
            details={"app_env": settings.app_env},
        )
    if "*" in settings.cors_origin_list:
        raise ValidationAppError(
            "CORS_ORIGINS must not include '*' in production",
        )
    # Soft ops checks — boot allowed, but privileged routes fail closed without keys.
    if not settings.n8n_webhook_configured:
        logger.warning("N8N_WEBHOOK_SECRET unset in production — n8n webhooks fail closed")
    if not settings.owner_api_key_configured:
        logger.warning("OWNER_API_KEY unset in production — API-key owner actions fail closed")
    has_bootstrap = bool(
        (settings.owner_bootstrap_email or "").strip()
        and settings.owner_bootstrap_password
        and settings.owner_bootstrap_password.get_secret_value().strip()
    )
    if not settings.owner_api_key_configured and not has_bootstrap:
        raise ValidationAppError(
            "Production requires OWNER_API_KEY or OWNER_BOOTSTRAP_EMAIL+PASSWORD for owner auth",
            details={"code": "CONFIGURATION_ERROR"},
        )
    if not settings.session_cookie_secure:
        logger.warning("SESSION_COOKIE_SECURE is false in production — set true behind HTTPS")
    if settings.browser_javascript_enabled:
        logger.warning(
            "BROWSER_JAVASCRIPT_ENABLED=true in production — SSRF surface is larger"
        )
    if settings.is_pilot_mode:
        logger.info("APP_ENV=production but OPERATING_MODE=pilot — Pilot Mode caps remain active")


# Re-export pilot deployment validator for callers that import from app.security
from app.security.pilot_config_validator import validate_pilot_deployment  # noqa: E402

__all__ = [
    "assert_daily_budget",
    "assert_max_single_expense",
    "assert_production_settings",
    "constant_time_equals",
    "daily_cost_total",
    "require_owner_identity",
    "validate_pilot_deployment",
    "validate_webhook_timestamp",
]
