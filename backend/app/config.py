from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_DIR = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_PROJECT_DIR / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Business Manager"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai_business_manager"

    max_ai_cost_usd_per_run: float = 5.0
    max_browser_pages_per_run: int = 20
    max_searches_per_run: int = 30
    max_emails_per_run: int = 10
    max_retries: int = 3
    max_execution_time_seconds: int = 300
    max_tasks_per_run: int = 50

    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    openai_retry_backoff_seconds_base: float = 1.0
    openai_retry_backoff_seconds_max: float = 30.0
    openai_prompt_token_cost_usd_per_1k_tokens: float = 0.0
    openai_completion_token_cost_usd_per_1k_tokens: float = 0.0
    tavily_api_key: SecretStr = Field(default=SecretStr(""))
    resend_api_key: SecretStr = Field(default=SecretStr(""))
    telegram_bot_token: SecretStr = Field(default=SecretStr(""))
    stripe_secret_key: SecretStr = Field(default=SecretStr(""))
    stripe_webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def database_is_configured(self) -> bool:
        return bool(self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
