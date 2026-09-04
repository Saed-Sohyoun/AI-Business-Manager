"""Phase 20 — security hardening tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.exceptions import ForbiddenError, LimitReachedError, UnauthorizedError, ValidationAppError
from app.providers.browser.request_guard import should_abort_browser_request
from app.providers.search.url_utils import is_allowed_url
from app.security import (
    assert_daily_budget,
    assert_max_single_expense,
    assert_production_settings,
    constant_time_equals,
    require_owner_identity,
    validate_webhook_timestamp,
)
from app.security.rate_limit import SlidingWindowRateLimiter


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        app_debug=False,
        log_level="WARNING",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="",
        max_single_expense=Decimal("25.00"),
        daily_budget_limit=Decimal("50.00"),
        approval_authorized_resolvers="owner,admin",
    )
    base.update(overrides)
    return Settings(**base)


# --- SSRF / browser request guard -------------------------------------------------


def test_browser_aborts_private_subresource():
    assert should_abort_browser_request("http://127.0.0.1/x.js", "script") is True
    assert should_abort_browser_request("http://169.254.169.254/latest", "xhr") is True
    assert should_abort_browser_request("http://[::1]/", "fetch") is True


def test_browser_aborts_unsafe_schemes_and_downloads():
    assert should_abort_browser_request("file:///etc/passwd", "document") is True
    assert should_abort_browser_request("javascript:alert(1)", "script") is True
    assert should_abort_browser_request("data:text/html,hi", "document") is True
    assert should_abort_browser_request("https://example.com/a.pdf", "download") is True


def test_browser_allows_about_blank_and_public_http():
    assert should_abort_browser_request("about:blank", "document") is False
    with patch(
        "app.providers.browser.request_guard.validate_browser_url",
        return_value=None,
    ):
        assert should_abort_browser_request("https://example.com/app.js", "script") is False


def test_search_blocks_ipv6_and_private_literals():
    assert is_allowed_url("https://ok.example/path") is True
    assert is_allowed_url("http://[::1]/") is False
    assert is_allowed_url("http://[fc00::1]/") is False
    assert is_allowed_url("http://10.0.0.5/") is False


# --- Financial ceilings -----------------------------------------------------------


def test_max_single_expense_enforced():
    cfg = _settings(max_single_expense=Decimal("25"))
    assert_max_single_expense(Decimal("25"), cfg)
    with pytest.raises(ForbiddenError) as exc:
        assert_max_single_expense(Decimal("25.01"), cfg)
    assert "max_single_expense" in exc.value.message


def test_daily_budget_enforced(db_session):
    from app.agents.finance import CostRecordRequest, FinanceAgent
    from app.approvals import ApprovalService
    from app.models.enums import CostCategory

    cfg = _settings(
        max_single_expense=Decimal("100"),
        daily_budget_limit=Decimal("40"),
    )
    agent = FinanceAgent(
        session=db_session,
        settings=cfg,
        approval_service=ApprovalService(db_session, cfg),
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("30"),
            category=CostCategory.OTHER_OPERATIONAL,
            source="security-test",
            description="seed",
            idempotency_key="sec-cost-seed",
        )
    )
    with pytest.raises(ForbiddenError) as exc:
        assert_daily_budget(db_session, cfg, additional=Decimal("15"))
    assert "Daily budget" in exc.value.message

    with pytest.raises((ForbiddenError, LimitReachedError)):
        agent.record_cost(
            CostRecordRequest(
                amount=Decimal("20"),
                category=CostCategory.OTHER_OPERATIONAL,
                source="security-test",
                description="over",
                idempotency_key="sec-cost-over",
            )
        )


# --- Webhook timestamp / compare --------------------------------------------------


def test_constant_time_equals_length_safe():
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abcd") is False
    assert constant_time_equals("", "x") is False
    assert constant_time_equals("same", "diff") is False


def test_webhook_timestamp_required_and_skew():
    now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    validate_webhook_timestamp(
        str(int(now.timestamp())),
        max_skew_seconds=300,
        now=now,
    )
    with pytest.raises(UnauthorizedError):
        validate_webhook_timestamp(None, max_skew_seconds=300, now=now)
    with pytest.raises(UnauthorizedError):
        validate_webhook_timestamp("not-a-number", max_skew_seconds=300, now=now)
    old = now - timedelta(seconds=301)
    with pytest.raises(UnauthorizedError):
        validate_webhook_timestamp(
            str(int(old.timestamp())),
            max_skew_seconds=300,
            now=now,
        )


def test_n8n_auth_rejects_stale_timestamp():
    import asyncio
    from unittest.mock import MagicMock

    from app.orchestration.auth import verify_n8n_webhook

    cfg = _settings(
        n8n_webhook_secret=SecretStr("super-secret-value"),
        n8n_webhook_require_timestamp=True,
        n8n_webhook_require_signature=False,
        n8n_webhook_max_skew_seconds=60,
    )
    stale = str(int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()))
    request = MagicMock()
    request.headers = {
        "X-N8N-Webhook-Secret": "super-secret-value",
        "X-N8N-Timestamp": stale,
    }
    request.app.state.settings = cfg

    async def _run():
        await verify_n8n_webhook(request, settings=cfg)

    with pytest.raises(UnauthorizedError):
        asyncio.run(_run())


# --- Owner auth stub --------------------------------------------------------------


def test_require_owner_identity():
    cfg = _settings(owner_api_key=SecretStr("owner-key-1"))
    assert require_owner_identity(provided_api_key="owner-key-1", settings=cfg) == "owner"
    with pytest.raises(UnauthorizedError):
        require_owner_identity(provided_api_key="wrong", settings=cfg)
    with pytest.raises(ForbiddenError):
        require_owner_identity(
            provided_api_key="owner-key-1",
            settings=cfg,
            claimed_resolver="intruder",
        )
    bare = _settings(owner_api_key=None)
    with pytest.raises(UnauthorizedError):
        require_owner_identity(provided_api_key="x", settings=bare)


# --- Rate limiter -----------------------------------------------------------------


def test_sliding_window_rate_limiter():
    lim = SlidingWindowRateLimiter()
    assert lim.allow("k", limit=2, window_seconds=60) is True
    assert lim.allow("k", limit=2, window_seconds=60) is True
    assert lim.allow("k", limit=2, window_seconds=60) is False
    lim.reset()
    assert lim.allow("k", limit=2, window_seconds=60) is True


def test_http_rate_limit_middleware_returns_429():
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.security.rate_limit import http_rate_limiter

    http_rate_limiter.reset()
    cfg = _settings(
        n8n_rate_limit_per_minute=10_000,
        api_rate_limit_per_minute=10_000,
        health_rate_limit_per_minute=2,
    )
    application = create_app(cfg)
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        blocked = client.get("/health")
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
    http_rate_limiter.reset()


# --- Production settings ----------------------------------------------------------


def test_production_settings_reject_debug_and_star_cors():
    with pytest.raises(ValidationAppError):
        assert_production_settings(
            _settings(app_env="production", app_debug=True, cors_origins="https://a.example")
        )
    with pytest.raises(ValidationAppError):
        assert_production_settings(
            _settings(app_env="production", app_debug=False, cors_origins="*")
        )
    # Non-production: no-op
    assert_production_settings(_settings(app_env="development", app_debug=True))


def test_manager_daily_budget_stop_reason():
    from app.agents.manager.limits import LimitSnapshot, evaluate_stop

    snap = LimitSnapshot(
        elapsed_seconds=1,
        estimated_cost=Decimal("10"),
        tasks_created=1,
        retries_used=0,
        max_runtime_seconds=300,
        max_cost=Decimal("100"),
        max_tasks=50,
        max_retries=3,
        daily_spend=Decimal("45"),
        daily_budget_limit=Decimal("50"),
    )
    decision = evaluate_stop(snap)
    assert decision.should_stop is True
    assert decision.reason == "daily_budget_limit"


def test_javascript_disabled_by_default():
    cfg = Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
    )
    assert cfg.browser_javascript_enabled is False
