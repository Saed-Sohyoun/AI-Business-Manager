from pydantic import SecretStr

from app.config import Settings, get_settings


def test_default_database_url_is_postgresql() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/ai_business_manager",
    )
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_is_configured() is True


def test_operational_limits_are_loaded() -> None:
    settings = get_settings()
    assert settings.max_ai_cost_usd_per_run > 0
    assert settings.max_browser_pages_per_run > 0
    assert settings.max_searches_per_run > 0
    assert settings.max_emails_per_run > 0
    assert settings.max_retries > 0
    assert settings.max_execution_time_seconds > 0
    assert settings.max_tasks_per_run > 0


def test_secret_fields_are_not_plain_strings() -> None:
    settings = get_settings()
    secret_fields = (
        settings.openai_api_key,
        settings.tavily_api_key,
        settings.resend_api_key,
        settings.telegram_bot_token,
        settings.stripe_secret_key,
        settings.stripe_webhook_secret,
    )
    assert all(isinstance(field, SecretStr) for field in secret_fields)


def test_settings_dump_does_not_expose_secret_values() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test-should-not-leak",
    )
    dumped = settings.model_dump()
    assert dumped["openai_api_key"] != "sk-test-should-not-leak"
    assert isinstance(dumped["openai_api_key"], SecretStr)
