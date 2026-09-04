"""Central application configuration via Pydantic Settings.

Provider API keys are optional so the API can start without OpenAI, Tavily,
or other external services configured. Provider calls fail clearly at request
time if the relevant API key is missing.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, centralized configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Business Operating System"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_debug: bool = False
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ai_business_os",
        description="SQLAlchemy database URL (PostgreSQL in production).",
    )
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_connect_timeout: int = Field(
        default=3,
        ge=1,
        le=60,
        description="Seconds to wait when opening a DB connection (keeps /health fail-fast).",
    )

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Centralized safety limits — Phase 22 Pilot Mode defaults
    max_agent_runtime_seconds: int = 300
    max_retries: int = 3
    max_tasks_per_run: int = 50
    max_ai_cost_per_run: Decimal = Decimal("5.00")
    daily_budget_limit: Decimal = Field(
        default=Decimal("3.00"),
        description="MAX_DAILY_SPENDING pilot default (EUR accounting units).",
    )
    max_single_expense: Decimal = Field(
        default=Decimal("20.00"),
        description="MAX_SINGLE_EXPENSE pilot default (EUR accounting units).",
    )
    max_outbound_messages_per_day: int = Field(
        default=5,
        ge=0,
        le=10_000,
        description="Legacy outbound email day cap (aligned with initial outreach).",
    )
    max_companies_per_day: int = Field(
        default=20,
        ge=0,
        le=10_000,
        description="MAX_COMPANIES_PER_DAY — companies created per UTC day.",
    )
    max_audits_per_day: int = Field(
        default=10,
        ge=0,
        le=10_000,
        description="MAX_AUDITS_PER_DAY — audits created per UTC day.",
    )
    max_initial_outreach_per_day: int = Field(
        default=5,
        ge=0,
        le=10_000,
        description="MAX_INITIAL_OUTREACH_PER_DAY — non-follow-up sends per UTC day.",
    )
    max_followups: int = Field(
        default=2,
        ge=0,
        le=50,
        description="MAX_FOLLOWUPS_PER_LEAD after the first send (pilot default 2).",
    )
    budget_warning_ratio: Decimal = Field(
        default=Decimal("0.70"),
        description="OwnerAlert INFO/IMPORTANT when daily spend reaches this fraction.",
    )
    budget_urgent_ratio: Decimal = Field(
        default=Decimal("0.90"),
        description="OwnerAlert URGENT when daily spend reaches this fraction.",
    )
    pilot_currency: str = Field(
        default="EUR",
        description="Display/accounting currency label for pilot budget messaging.",
    )
    operating_mode: Literal["pilot", "production"] = Field(
        default="pilot",
        description="Pilot Mode is the safe default. Production requires ALLOW_PRODUCTION_MODE.",
    )
    allow_production_mode: bool = Field(
        default=False,
        description="Must be explicitly true to set OPERATING_MODE=production (fail closed).",
    )
    followup_delay_days_first: int = Field(
        default=3,
        ge=1,
        le=30,
        description="Days after initial send before the first follow-up may be due.",
    )
    followup_delay_days_second: int = Field(
        default=7,
        ge=1,
        le=60,
        description="Days after first follow-up before the second follow-up may be due.",
    )
    approval_required_for_external_actions: bool = True
    approval_default_ttl_seconds: int = Field(
        default=86_400,
        ge=60,
        le=30 * 24 * 3600,
        description="Default approval expiry window in seconds.",
    )
    approval_authorized_resolvers: str = Field(
        default="owner,admin",
        description="Comma-separated identities allowed to approve/reject (never agents).",
    )

    # Optional providers — never required for application startup
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI chat model.")
    openai_timeout: float = Field(
        default=60.0,
        ge=1.0,
        le=600.0,
        description="Per-request timeout in seconds for OpenAI calls.",
    )
    openai_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Provider-level retries for transient OpenAI failures.",
    )
    tavily_api_key: SecretStr | None = None
    tavily_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Per-request timeout in seconds for Tavily search calls.",
    )
    tavily_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Provider-level retries for transient Tavily failures.",
    )
    tavily_max_results: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Hard cap on search results returned to callers.",
    )
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_cost_per_request: Decimal = Field(
        default=Decimal("0.01"),
        description="Estimated USD cost per Tavily search request (internal accounting).",
    )

    # Browser (Playwright) — optional; app boots without browsers installed
    browser_enabled: bool = True
    browser_headless: bool = True
    browser_javascript_enabled: bool = Field(
        default=False,
        description="Phase 20 default off — reduces SSRF via JS-driven subrequests. Enable only when needed.",
    )
    browser_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Overall browser operation timeout in seconds.",
    )
    browser_navigation_timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=120.0,
        description="Navigation timeout in seconds.",
    )
    browser_max_page_size_bytes: int = Field(
        default=2_000_000,
        ge=1_000,
        le=10_000_000,
        description="Reject responses larger than this Content-Length when known.",
    )
    browser_max_text_chars: int = Field(
        default=50_000,
        ge=100,
        le=500_000,
        description="Maximum visible text characters retained from a page.",
    )
    browser_max_links: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of links retained from a page.",
    )
    browser_max_redirects: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Maximum HTTP redirects allowed during navigation.",
    )
    browser_max_metadata_items: int = Field(
        default=40,
        ge=1,
        le=200,
        description="Maximum metadata key/value pairs retained.",
    )

    # Research agent limits
    max_companies_per_run: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Hard cap on companies stored per Research Agent run.",
    )
    research_search_results_per_query: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Search results requested per research query page.",
    )
    research_max_search_pages: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum search pages/queries attempted per run (pagination bound).",
    )
    research_verify_with_browser: bool = Field(
        default=True,
        description="When true, attempt browser verification of candidate websites.",
    )
    research_browser_timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=120.0,
        description="Per-candidate browser verification timeout.",
    )

    # Audit agent limits
    max_audits_per_run: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Hard cap on company audits per Audit Agent run.",
    )
    audit_use_ai: bool = Field(
        default=True,
        description="When true and AI is configured, enrich deterministic findings via structured AI.",
    )
    audit_search_results: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Optional search results gathered per company during audit (0 disables).",
    )

    # Sales agent — draft only in Phase 10
    sales_use_ai: bool = Field(
        default=True,
        description="When true and AI is configured, polish deterministic outreach drafts.",
    )
    max_outreaches_per_run: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Hard cap on outreach drafts per Sales Agent run (single-lead runs use 1).",
    )

    resend_api_key: SecretStr | None = None
    email_from: str | None = Field(
        default=None,
        description="Default From address for outbound email (required to send).",
    )
    resend_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Per-request timeout in seconds for Resend API calls.",
    )
    resend_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Provider-level retries for transient Resend failures.",
    )
    resend_cost_per_email: Decimal = Field(
        default=Decimal("0.001"),
        description="Estimated USD cost per outbound email (internal accounting).",
    )
    stripe_secret_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = Field(
        default=None,
        description="Telegram chat ID for owner notifications (required to send).",
    )
    telegram_timeout: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        description="Per-request timeout in seconds for Telegram Bot API calls.",
    )
    telegram_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Provider-level retries for transient Telegram failures.",
    )
    notification_max_per_hour: int = Field(
        default=12,
        ge=1,
        le=100,
        description="Anti-spam cap on SENT notifications per rolling hour.",
    )
    notification_max_info_per_day: int = Field(
        default=3,
        ge=0,
        le=50,
        description="Anti-spam cap on INFO notifications per rolling day.",
    )
    notification_min_priority: str = Field(
        default="important",
        description="Minimum priority to deliver (info|important|urgent|critical).",
    )

    # n8n orchestration — schedule/trigger only; business logic stays in backend
    n8n_webhook_secret: SecretStr | None = None
    n8n_webhook_header: str = Field(
        default="X-N8N-Webhook-Secret",
        description="Header carrying the shared n8n webhook secret.",
    )
    n8n_webhook_max_skew_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Max age/skew for X-N8N-Timestamp (replay mitigation).",
    )
    n8n_webhook_require_timestamp: bool = Field(
        default=True,
        description="When true, n8n webhooks must send X-N8N-Timestamp (Unix epoch seconds).",
    )
    n8n_webhook_require_signature: bool = Field(
        default=True,
        description=(
            "When true, n8n webhooks must send X-N8N-Signature (HMAC-SHA256) "
            "and X-N8N-Nonce for replay protection."
        ),
    )
    n8n_default_timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=600.0,
        description="Default per-workflow execution timeout (backend soft deadline).",
    )
    n8n_max_execution_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Max backend retries for a failed/timed-out execution with the same idempotency key.",
    )
    n8n_rate_limit_per_minute: int = Field(
        default=30,
        ge=1,
        le=10_000,
        description="HTTP rate limit for /api/v1/n8n/* per client IP.",
    )
    api_rate_limit_per_minute: int = Field(
        default=120,
        ge=1,
        le=10_000,
        description="Default HTTP rate limit for other API paths per client IP.",
    )
    health_rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        le=10_000,
        description="HTTP rate limit for /health per client IP.",
    )

    # Owner HTTP actions — API key is emergency/local only; prefer session auth
    owner_api_key: SecretStr | None = None
    owner_bootstrap_email: str = Field(
        default="",
        description="When set with OWNER_BOOTSTRAP_PASSWORD, creates first owner if none exist.",
    )
    owner_bootstrap_password: SecretStr | None = None
    owner_session_ttl_hours: int = Field(default=12, ge=1, le=168)
    owner_login_rate_limit_per_minute: int = Field(default=10, ge=1, le=100)
    session_cookie_secure: bool = Field(
        default=False,
        description="Set true in production so session cookie requires HTTPS.",
    )

    @property
    def openai_configured(self) -> bool:
        """True when an OpenAI API key is present (does not validate the key)."""
        if self.openai_api_key is None:
            return False
        return bool(self.openai_api_key.get_secret_value().strip())

    @property
    def tavily_configured(self) -> bool:
        """True when a Tavily API key is present (does not validate the key)."""
        if self.tavily_api_key is None:
            return False
        return bool(self.tavily_api_key.get_secret_value().strip())

    @property
    def telegram_configured(self) -> bool:
        """True when Telegram bot token and chat ID are present."""
        if self.telegram_bot_token is None:
            return False
        if not self.telegram_bot_token.get_secret_value().strip():
            return False
        if not (self.telegram_chat_id or "").strip():
            return False
        return True

    @property
    def resend_configured(self) -> bool:
        """True when a Resend API key is present (does not validate the key)."""
        if self.resend_api_key is None:
            return False
        return bool(self.resend_api_key.get_secret_value().strip())

    @property
    def n8n_webhook_configured(self) -> bool:
        """True when an n8n webhook shared secret is present."""
        if self.n8n_webhook_secret is None:
            return False
        return bool(self.n8n_webhook_secret.get_secret_value().strip())

    @property
    def owner_api_key_configured(self) -> bool:
        """True when an owner API key is present for privileged HTTP actions."""
        if self.owner_api_key is None:
            return False
        return bool(self.owner_api_key.get_secret_value().strip())

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        prefix = value.strip() or "/api/v1"
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return prefix.rstrip("/") or "/api/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def is_pilot_mode(self) -> bool:
        """True unless operating_mode is production (which requires an explicit unlock)."""
        return self.operating_mode != "production"

    @model_validator(mode="after")
    def prevent_accidental_production_mode(self) -> Settings:
        if self.operating_mode == "production" and not self.allow_production_mode:
            raise ValueError(
                "OPERATING_MODE=production requires ALLOW_PRODUCTION_MODE=true "
                "(Pilot Mode is the safe default)"
            )
        return self

    def masked_database_url(self) -> str:
        """Return DATABASE_URL with password redacted for logs."""
        url = self.database_url
        if "@" not in url or "://" not in url:
            return url
        scheme, remainder = url.split("://", 1)
        if "@" not in remainder:
            return url
        credentials, host_part = remainder.rsplit("@", 1)
        if ":" in credentials:
            user, _password = credentials.split(":", 1)
            return f"{scheme}://{user}:***@{host_part}"
        return f"{scheme}://***@{host_part}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton for dependency injection."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache (used by tests)."""
    get_settings.cache_clear()
