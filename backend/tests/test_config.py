"""Configuration and settings tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import Settings, clear_settings_cache, get_settings


def test_settings_defaults_are_safe_for_boot():
    clear_settings_cache()
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        app_env="test",
        max_outbound_messages_per_day=5,
        max_followups=2,
    )
    assert settings.app_name
    assert settings.openai_api_key is None
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.openai_timeout == 60.0
    assert settings.openai_max_retries == 3
    assert settings.openai_configured is False
    assert settings.tavily_api_key is None
    assert settings.tavily_configured is False
    assert settings.tavily_max_results == 10
    assert settings.browser_enabled is True
    assert settings.browser_max_redirects == 5
    assert settings.max_companies_per_run == 20
    assert settings.max_audits_per_run == 10
    assert settings.max_outbound_messages_per_day == 5
    assert settings.max_followups == 2
    assert settings.approval_required_for_external_actions is True
    assert settings.resend_configured is False
    assert settings.max_retries == 3
    assert settings.daily_budget_limit == Decimal("3.00")
    assert settings.max_single_expense == Decimal("20.00")
    assert settings.max_companies_per_day == 20
    assert settings.operating_mode == "pilot"


def test_masked_database_url_hides_password():
    settings = Settings(
        database_url="postgresql+psycopg://user:supersecret@localhost:5432/ai_business_os"
    )
    masked = settings.masked_database_url()
    assert "supersecret" not in masked
    assert "user:***@" in masked


def test_cors_origin_list_parsing():
    settings = Settings(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        Settings(log_level="VERBOSE")


def test_get_settings_cache_roundtrip(monkeypatch):
    clear_settings_cache()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    first = get_settings()
    second = get_settings()
    assert first is second
    clear_settings_cache()
