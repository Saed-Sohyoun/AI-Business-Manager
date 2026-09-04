"""Mocked AI provider / AIService tests — no live OpenAI calls."""

from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel, SecretStr

from app.config import Settings
from app.providers.ai.costing import estimate_cost_usd, total_tokens
from app.providers.ai.exceptions import (
    AIConfigurationError,
    AIMalformedResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from app.providers.ai.openai_provider import OpenAIProvider
from app.providers.ai.safe_logging import sanitize_metadata
from app.providers.ai.types import AICompletionRequest
from app.services.ai_service import AIService, build_ai_service


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        openai_api_key=SecretStr("sk-test-secret-key-do-not-log"),
        openai_model="gpt-4o-mini",
        openai_timeout=30.0,
        openai_max_retries=2,
        database_url="sqlite+pysqlite:///:memory:",
    )
    base.update(overrides)
    return Settings(**base)


def _mock_completion(
    *,
    content: str = "ok",
    prompt_tokens: int = 12,
    completion_tokens: int = 4,
    model: str = "gpt-4o-mini",
    request_id: str = "chatcmpl-test-1",
):
    return SimpleNamespace(
        id=request_id,
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request, headers={"retry-after": "0"})
    return RateLimitError(
        "Rate limit exceeded",
        response=response,
        body={"error": {"message": "Rate limit exceeded"}},
    )


def _timeout_error() -> APITimeoutError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return APITimeoutError(request=request)


class _ScoreResult(BaseModel):
    score: int
    category: str


@pytest.fixture()
def mock_client():
    client = MagicMock()
    client.chat.completions.create = MagicMock(return_value=_mock_completion())
    return client


def test_successful_response(mock_client):
    provider = OpenAIProvider(_settings(), client=mock_client, sleep_fn=lambda _s: None)
    service = AIService(provider)

    response = service.complete(
        system_instruction="You are a concise analyst.",
        user_message="Summarize Acme.",
        metadata={"task": "research_summary", "company_id": "c1"},
    )

    assert response.content == "ok"
    assert response.model == "gpt-4o-mini"
    assert response.input_tokens == 12
    assert response.output_tokens == 4
    assert response.total_tokens == 16
    assert response.request_id == "chatcmpl-test-1"
    assert response.provider == "openai"
    assert response.estimated_cost > Decimal("0")
    assert response.latency_ms >= 0
    assert response.metadata["task"] == "research_summary"
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"][0]["role"] == "system"
    assert call_kwargs["messages"][1]["role"] == "user"


def test_invalid_configuration_fails_only_on_request():
    settings = _settings(openai_api_key=None)
    provider = OpenAIProvider(settings)
    service = build_ai_service(settings, provider=provider)

    assert service.is_configured() is False

    with pytest.raises(AIConfigurationError) as exc_info:
        service.complete(user_message="hello")

    assert "OPENAI_API_KEY" in exc_info.value.message
    assert exc_info.value.code == "ai_configuration_error"


def test_app_starts_without_openai_key(settings):
    from app.main import create_app
    from fastapi.testclient import TestClient

    assert settings.openai_api_key is None
    application = create_app(settings)
    with TestClient(application) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_timeout_maps_to_ai_timeout(mock_client):
    mock_client.chat.completions.create.side_effect = _timeout_error()
    provider = OpenAIProvider(
        _settings(openai_max_retries=0),
        client=mock_client,
        sleep_fn=lambda _s: None,
    )

    with pytest.raises(AITimeoutError):
        provider.complete(AICompletionRequest(user_message="ping"))


def test_rate_limit_maps_to_ai_rate_limit(mock_client):
    mock_client.chat.completions.create.side_effect = _rate_limit_error()
    provider = OpenAIProvider(
        _settings(openai_max_retries=0),
        client=mock_client,
        sleep_fn=lambda _s: None,
    )

    with pytest.raises(AIRateLimitError):
        provider.complete(AICompletionRequest(user_message="ping"))


def test_retry_on_rate_limit_then_success(mock_client):
    mock_client.chat.completions.create.side_effect = [
        _rate_limit_error(),
        _mock_completion(content="recovered"),
    ]
    sleeps: list[float] = []
    provider = OpenAIProvider(
        _settings(openai_max_retries=2),
        client=mock_client,
        sleep_fn=lambda s: sleeps.append(s),
    )

    response = provider.complete(AICompletionRequest(user_message="ping"))

    assert response.content == "recovered"
    assert response.attempts == 2
    assert mock_client.chat.completions.create.call_count == 2
    assert sleeps  # backoff invoked


def test_malformed_response_missing_choices(mock_client):
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        id="x",
        model="gpt-4o-mini",
        choices=[],
        usage=None,
    )
    provider = OpenAIProvider(_settings(), client=mock_client)

    with pytest.raises(AIMalformedResponseError):
        provider.complete(AICompletionRequest(user_message="ping"))


def test_malformed_structured_json(mock_client):
    mock_client.chat.completions.create.return_value = _mock_completion(content="not-json{")
    provider = OpenAIProvider(_settings(), client=mock_client)
    service = AIService(provider)

    with pytest.raises(AIMalformedResponseError):
        service.complete_structured(
            user_message="score this",
            response_model=_ScoreResult,
            system_instruction="Return JSON only.",
        )


def test_structured_success(mock_client):
    mock_client.chat.completions.create.return_value = _mock_completion(
        content='{"score": 88, "category": "hot"}'
    )
    provider = OpenAIProvider(_settings(), client=mock_client)
    service = AIService(provider)

    response, parsed = service.complete_structured(
        user_message="score lead",
        response_model=_ScoreResult,
    )

    assert parsed.score == 88
    assert parsed.category == "hot"
    assert response.structured_data == {"score": 88, "category": "hot"}
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"]["type"] == "json_schema"


def test_usage_calculation_and_cost_estimation():
    assert total_tokens(10, 5) == 15
    assert total_tokens(None, None) is None

    cost = estimate_cost_usd(model="gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == Decimal("0.750000")  # 0.15 + 0.60

    response = OpenAIProvider(
        _settings(),
        client=MagicMock(
            chat=MagicMock(
                completions=MagicMock(
                    create=MagicMock(
                        return_value=_mock_completion(prompt_tokens=1000, completion_tokens=500)
                    )
                )
            )
        ),
        sleep_fn=lambda _s: None,
    ).complete(AICompletionRequest(user_message="cost check"))

    expected = estimate_cost_usd(model="gpt-4o-mini", input_tokens=1000, output_tokens=500)
    assert response.estimated_cost == expected
    assert response.total_tokens == 1500


def test_secret_protection_in_logs(mock_client, caplog):
    secret = "sk-test-secret-key-do-not-log"
    sensitive_prompt = "Customer email jane.doe@example.com phone +491234"
    provider = OpenAIProvider(_settings(openai_api_key=SecretStr(secret)), client=mock_client)

    with caplog.at_level(logging.INFO, logger="app.providers.ai.safe_logging"):
        provider.complete(
            AICompletionRequest(
                user_message=sensitive_prompt,
                system_instruction="Confidential system brief",
                metadata={"email": "jane.doe@example.com", "task": "audit"},
            )
        )

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in joined
    assert "jane.doe@example.com" not in joined
    assert "+491234" not in joined
    assert "Confidential system brief" not in joined
    assert "user_chars=" in joined
    assert "[redacted]" in joined or "task" in joined


def test_sanitize_metadata_redacts_sensitive_keys():
    safe = sanitize_metadata(
        {
            "task": "score",
            "email": "a@b.c",
            "user_message": "should hide",
            "note": "x" * 200,
        }
    )
    assert safe["task"] == "score"
    assert safe["email"] == "[redacted]"
    assert safe["user_message"] == "[redacted]"
    assert safe["note"].endswith("...")


def test_provider_error_non_retryable_does_not_loop(mock_client):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(400, request=request)
    from openai import BadRequestError

    mock_client.chat.completions.create.side_effect = BadRequestError(
        "bad request",
        response=response,
        body={"error": {"message": "bad request"}},
    )
    provider = OpenAIProvider(
        _settings(openai_max_retries=3),
        client=mock_client,
        sleep_fn=lambda _s: None,
    )

    with pytest.raises(AIProviderError):
        provider.complete(AICompletionRequest(user_message="ping"))

    assert mock_client.chat.completions.create.call_count == 1


def test_ai_service_and_base_do_not_import_openai_sdk():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    forbidden_files = [
        root / "services" / "ai_service.py",
        root / "providers" / "ai" / "base.py",
        root / "providers" / "ai" / "types.py",
        root / "providers" / "ai" / "costing.py",
        root / "providers" / "ai" / "schema_utils.py",
    ]
    for path in forbidden_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "openai" and not alias.name.startswith("openai.")
            if isinstance(node, ast.ImportFrom):
                assert node.module != "openai"
                assert not (node.module or "").startswith("openai.")


def test_prepare_openai_strict_schema_sets_required_and_additional_properties():
    from app.providers.ai.schema_utils import prepare_openai_strict_schema

    schema = {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "category": {"type": "string"},
        },
    }
    adapted = prepare_openai_strict_schema(schema)
    assert adapted["additionalProperties"] is False
    assert set(adapted["required"]) == {"score", "category"}
    # Original untouched
    assert "required" not in schema
