"""Owner readiness aggregation — Wave 5 pilot launch gate (read-only)."""

from __future__ import annotations

import os
from decimal import Decimal

from app.config import Settings
from app.owner.schemas_pilot import ReadinessCheck, ReadinessView
from app.security.pilot_config_validator import validate_pilot_deployment


def _env_tri_state(name: str) -> str:
    """Return true|false|unset for readiness env gates."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return "unset"
    val = str(raw).strip().lower()
    if val in {"1", "true", "yes", "pass", "ok"}:
        return "true"
    if val in {"0", "false", "no", "fail"}:
        return "false"
    return "unset"


def _is_postgres(url: str) -> bool:
    lower = (url or "").lower()
    return lower.startswith("postgresql") or lower.startswith("postgres")


class ReadinessService:
    """Compute READY_FOR_PILOT / NOT_READY without unlocking anything or exposing secrets."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self) -> ReadinessView:
        checks: list[ReadinessCheck] = []
        settings = self._settings

        # Database
        if _is_postgres(settings.database_url):
            checks.append(
                ReadinessCheck(
                    id="database",
                    label="Database engine",
                    status="pass",
                    detail="PostgreSQL configured",
                )
            )
        else:
            engine = "sqlite" if "sqlite" in settings.database_url.lower() else "other"
            checks.append(
                ReadinessCheck(
                    id="database",
                    label="Database engine",
                    status="fail",
                    detail=f"{engine} is not ready for pilot (PostgreSQL required)",
                )
            )

        # Auth
        has_api = settings.owner_api_key_configured
        has_bootstrap = bool(
            (settings.owner_bootstrap_email or "").strip()
            and settings.owner_bootstrap_password
            and settings.owner_bootstrap_password.get_secret_value().strip()
        )
        if has_api or has_bootstrap:
            checks.append(
                ReadinessCheck(
                    id="auth",
                    label="Owner auth configured",
                    status="pass",
                    detail="Owner API key or bootstrap credentials present",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    id="auth",
                    label="Owner auth configured",
                    status="fail",
                    detail="Neither OWNER_API_KEY nor bootstrap credentials configured",
                )
            )

        # Providers — boolean only
        providers = {
            "openai": settings.openai_configured,
            "tavily": settings.tavily_configured,
            "resend": settings.resend_configured,
            "telegram": settings.telegram_configured,
        }
        any_provider = any(providers.values())
        checks.append(
            ReadinessCheck(
                id="providers",
                label="Providers configured",
                status="pass" if any_provider else "warn",
                detail="At least one external provider configured"
                if any_provider
                else "No external providers configured (optional for boot)",
            )
        )

        # Limits within pilot envelope
        limits_ok = (
            settings.max_companies_per_day <= 20
            and settings.max_audits_per_day <= 10
            and settings.max_initial_outreach_per_day <= 5
            and settings.max_followups <= 2
            and settings.daily_budget_limit <= Decimal("3.00")
            and settings.max_single_expense <= Decimal("20.00")
        )
        checks.append(
            ReadinessCheck(
                id="limits",
                label="Pilot limits",
                status="pass" if limits_ok else "fail",
                detail="Within pilot caps"
                if limits_ok
                else "Configured limits exceed pilot envelope",
            )
        )

        # Production locked
        locked = not settings.allow_production_mode
        checks.append(
            ReadinessCheck(
                id="production_locked",
                label="Production mode locked",
                status="pass" if locked else "fail",
                detail="ALLOW_PRODUCTION_MODE is false"
                if locked
                else "Production unlock is enabled",
            )
        )

        # n8n secret
        checks.append(
            ReadinessCheck(
                id="n8n_secret",
                label="n8n webhook secret",
                status="pass" if settings.n8n_webhook_configured else "fail",
                detail="Configured" if settings.n8n_webhook_configured else "Not configured",
            )
        )

        # Session cookie secure expectation for pilot-like / production
        if settings.is_production:
            secure_ok = settings.session_cookie_secure
            checks.append(
                ReadinessCheck(
                    id="session_cookie_secure",
                    label="Session cookie secure",
                    status="pass" if secure_ok else "fail",
                    detail="SESSION_COOKIE_SECURE required for production"
                    if not secure_ok
                    else "HTTPS session cookie enabled",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    id="session_cookie_secure",
                    label="Session cookie secure",
                    status="pass" if settings.session_cookie_secure else "warn",
                    detail="Recommended true for pilot-like HTTPS deploy"
                    if not settings.session_cookie_secure
                    else "HTTPS session cookie enabled",
                )
            )

        # Debug off for production-like
        if settings.is_production and settings.app_debug:
            checks.append(
                ReadinessCheck(
                    id="debug",
                    label="Debug disabled",
                    status="fail",
                    detail="APP_DEBUG must be false in production",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    id="debug",
                    label="Debug disabled",
                    status="pass",
                    detail="OK",
                )
            )

        # CORS wildcard + credentials
        if "*" in settings.cors_origin_list:
            checks.append(
                ReadinessCheck(
                    id="cors",
                    label="CORS origins",
                    status="fail",
                    detail="Wildcard CORS incompatible with credentialed sessions",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    id="cors",
                    label="CORS origins",
                    status="pass",
                    detail="No wildcard origins",
                )
            )

        # Concurrency suite — env POSTGRES_CONCURRENCY_PASS
        conc = _env_tri_state("POSTGRES_CONCURRENCY_PASS")
        if conc == "true":
            checks.append(
                ReadinessCheck(
                    id="concurrency_suite",
                    label="Postgres concurrency suite",
                    status="pass",
                    detail="POSTGRES_CONCURRENCY_PASS=true",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    id="concurrency_suite",
                    label="Postgres concurrency suite",
                    status="fail",
                    detail="POSTGRES_CONCURRENCY_PASS unset or false — treat as BLOCKED",
                )
            )

        # Backup restore — env BACKUP_RESTORE_PASS
        backup = _env_tri_state("BACKUP_RESTORE_PASS")
        if backup == "true":
            checks.append(
                ReadinessCheck(
                    id="backup_status",
                    label="Backup/restore validation",
                    status="pass",
                    detail="BACKUP_RESTORE_PASS=true",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    id="backup_status",
                    label="Backup/restore validation",
                    status="fail",
                    detail="BACKUP_RESTORE_PASS unset or false — treat as BLOCKED",
                )
            )

        # Fold validator issues (no secrets)
        validation = validate_pilot_deployment(settings)
        for issue in validation.issues:
            # Avoid duplicating checks already covered above
            if issue.code in {
                "database_postgres",
                "n8n_secret",
                "auth_configured",
                "session_cookie_secure",
                "cors_wildcard",
                "debug_false",
            }:
                continue
            checks.append(
                ReadinessCheck(
                    id=issue.code,
                    label=issue.code,
                    status="fail" if issue.severity == "fail" else "warn",
                    detail=issue.message,
                )
            )

        failing = sum(1 for c in checks if c.status == "fail")
        overall = "READY_FOR_PILOT" if failing == 0 else "NOT_READY"
        return ReadinessView(
            overall=overall,
            checks=checks,
            failing_count=failing,
            production_locked=locked,
            providers=providers,
        )
