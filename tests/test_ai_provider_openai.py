import asyncio
from types import SimpleNamespace

from pydantic import SecretStr

from services.ai_provider.errors import AIRateLimitError, AIMissingProviderConfigurationError
from services.ai_provider.openai_provider import OpenAIProvider
from services.ai_provider.schemas import AIProviderChatResponse, AIUsage, ChatMessage


async def _run() -> None:
    # Basic happy path (mocked OpenAI response)
    captured = {}

    async def mock_create(*, model: str, messages: list[dict[str, str]], **_kwargs):
        captured["model"] = model
        captured["messages"] = messages
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Hello from OpenAI"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    mock_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)))
    provider = OpenAIProvider(api_key=SecretStr("sk-test"), client=mock_client)

    result = await provider.chat(
        model="gpt-test",
        system_instruction="You are a bot.",
        messages=[ChatMessage(role="user", content="Hi")],
    )

    assert isinstance(result, AIProviderChatResponse)
    assert result.content == "Hello from OpenAI"
    assert result.finish_reason == "stop"
    assert result.model == "gpt-test"
    assert result.usage == AIUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    assert captured["model"] == "gpt-test"
    assert captured["messages"][0] == {"role": "system", "content": "You are a bot."}
    assert captured["messages"][1] == {"role": "user", "content": "Hi"}

    # Missing key should fail only on request time.
    provider_missing_key = OpenAIProvider(api_key=SecretStr(""), client=mock_client)
    try:
        await provider_missing_key.chat(
            model="gpt-test",
            system_instruction=None,
            messages=[ChatMessage(role="user", content="Hi")],
        )
        assert False, "Expected missing-key error"
    except AIMissingProviderConfigurationError:
        pass

    # Rate limit mapping (OpenAI 429 -> AIRateLimitError)
    class Dummy429(Exception):
        status_code = 429

    async def mock_create_rate_limit(*_args, **_kwargs):
        raise Dummy429("rate limit")

    mock_client_rate_limit = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=mock_create_rate_limit)
        )
    )
    provider_rate_limit = OpenAIProvider(api_key=SecretStr("sk-test"), client=mock_client_rate_limit)

    try:
        await provider_rate_limit.chat(
            model="gpt-test",
            system_instruction=None,
            messages=[ChatMessage(role="user", content="Hi")],
        )
        assert False, "Expected rate limit error"
    except AIRateLimitError:
        pass


def test_openai_provider_chat_is_mockable() -> None:
    asyncio.run(_run())

