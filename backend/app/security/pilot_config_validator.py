"""Pilot / production deployment validation for readiness (stricter than boot)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.config import Settings


@dataclass
class PilotValidationIssue:
    code: str
    message: str
    severity: str = "fail"  # fail | warn


@dataclass
class PilotValidationResult:
    ok: bool
    issues: list[PilotValidationIssue] = field(default_factory=list)

    def add(self, code: str, message: str, *, severity: str = "fail") -> None:
        self.issues.append(PilotValidationIssue(code=code, message=message, severity=severity))
        if severity == "fail":
            self.ok = False


def _is_postgres(url: str) -> bool:
    lower = (url or "").lower()
    return lower.startswith("postgresql") or lower.startswith("postgres")


def validate_pilot_deployment(settings: Settings) -> PilotValidationResult:
    """Stricter checks for READY_FOR_PILOT — does not unlock production or mutate settings.

    Critical production boot issues still belong to assert_production_settings.
    This helper is used by owner readiness and may report fail without aborting boot.
    """
    result = PilotValidationResult(ok=True)

    if not _is_postgres(settings.database_url):
        result.add("database_postgres", "PostgreSQL required for pilot readiness (sqlite not ready)")

    if settings.is_production and settings.app_debug:
        result.add("debug_false", "APP_DEBUG must be false in production")

    if "*" in settings.cors_origin_list:
        result.add(
            "cors_wildcard",
            "Wildcard CORS is incompatible with credentialed sessions",
        )

    if not settings.allow_production_mode:
        # Expected locked state — pass signal for readiness consumers
        pass
    else:
        result.add(
            "production_unlocked",
            "ALLOW_PRODUCTION_MODE is true — pilot gate expects production locked",
            severity="warn",
        )

    if not settings.n8n_webhook_configured:
        result.add("n8n_secret", "N8N_WEBHOOK_SECRET must be configured for pilot readiness")

    auth_ok = settings.owner_api_key_configured or bool(
        (settings.owner_bootstrap_email or "").strip()
        and settings.owner_bootstrap_password
        and settings.owner_bootstrap_password.get_secret_value().strip()
    )
    if not auth_ok:
        result.add("auth_configured", "Owner auth not configured (API key or bootstrap credentials)")

    # SESSION_COOKIE_SECURE: required for production app_env; recommended for pilot-like
    if settings.is_production and not settings.session_cookie_secure:
        result.add(
            "session_cookie_secure",
            "SESSION_COOKIE_SECURE must be true in production",
        )
    elif not settings.session_cookie_secure:
        result.add(
            "session_cookie_secure",
            "SESSION_COOKIE_SECURE recommended true for pilot-like HTTPS deploy",
            severity="warn",
        )

    # Pilot limits must not exceed Wave envelope
    if settings.max_companies_per_day > 20:
        result.add("limits_companies", "max_companies_per_day exceeds pilot cap 20")
    if settings.max_audits_per_day > 10:
        result.add("limits_audits", "max_audits_per_day exceeds pilot cap 10")
    if settings.max_initial_outreach_per_day > 5:
        result.add("limits_outreach", "max_initial_outreach_per_day exceeds pilot cap 5")
    if settings.max_followups > 2:
        result.add("limits_followups", "max_followups exceeds pilot cap 2")
    if settings.daily_budget_limit > Decimal("3.00"):
        result.add("limits_budget", "daily_budget_limit exceeds pilot cap €3")
    if settings.max_single_expense > Decimal("20.00"):
        result.add("limits_expense", "max_single_expense exceeds pilot cap €20")

    return result
