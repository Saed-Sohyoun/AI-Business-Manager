import asyncio

from services.ai_provider.errors import AIRateLimitError
from services.ai_provider.interface import AIProvider
from services.ai_provider.schemas import AIProviderChatResponse, AIUsage, ChatMessage
from services.ai_service import AIService


class FakeProviderRetryOnce:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, *, model: str, system_instruction: str | None, messages):  # type: ignore[override]
        self.calls += 1
        if self.calls == 1:
            raise AIRateLimitError("rate limited")

        return AIProviderChatResponse(
            model=model,
            content="OK",
            finish_reason="stop",
            usage=AIUsage(prompt_tokens=1000, completion_tokens=2000, total_tokens=3000),
        )


class FakeProviderAlwaysTimeout:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, *, model: str, system_instruction: str | None, messages):  # type: ignore[override]
        self.calls += 1
        await asyncio.sleep(0.05)
        return AIProviderChatResponse(
            model=model,
            content="should-not-return",
            finish_reason="stop",
            usage=AIUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


def test_ai_service_retries_rate_limit_and_estimates_cost() -> None:
    provider = FakeProviderRetryOnce()
    service = AIService(
        provider=provider,  # type: ignore[arg-type]
        model="gpt-test",
        timeout_seconds=1.0,
        max_retries=2,
        retry_backoff_seconds_base=0.0,
        retry_backoff_seconds_max=0.0,
        prompt_cost_usd_per_1k_tokens=0.01,
        completion_cost_usd_per_1k_tokens=0.02,
        max_cost_usd_per_run=None,
    )

    async def _run() -> None:
        response = await service.chat(
            system_instruction="sys",
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert provider.calls == 2
        assert response.content == "OK"
        assert response.attempts == 2
        assert response.estimated_cost_usd is not None
        # (1000/1000)*0.01 + (2000/1000)*0.02 = 0.01 + 0.04 = 0.05
        assert abs(response.estimated_cost_usd - 0.05) < 1e-9
        assert response.usage is not None
        assert response.usage.total_tokens == 3000

    asyncio.run(_run())


def test_ai_service_timeout_is_limited_retries() -> None:
    provider = FakeProviderAlwaysTimeout()
    service = AIService(
        provider=provider,  # type: ignore[arg-type]
        model="gpt-test",
        timeout_seconds=0.01,
        max_retries=1,
        retry_backoff_seconds_base=0.0,
        retry_backoff_seconds_max=0.0,
        prompt_cost_usd_per_1k_tokens=0.0,
        completion_cost_usd_per_1k_tokens=0.0,
        max_cost_usd_per_run=None,
    )

    async def _run() -> None:
        try:
            await service.chat(system_instruction=None, messages=[ChatMessage(role="user", content="hi")])
        except Exception as exc:  # noqa: BLE001
            # Must not retry forever.
            assert provider.calls == 2
            assert "timed out" in str(exc).lower()
        else:
            assert False, "Expected timeout exception"

    asyncio.run(_run())

