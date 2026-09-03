from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Sequence

from pydantic import BaseModel

from app.config import Settings, get_settings
from services.ai_provider.errors import (
    AIProviderError,
    AIRateLimitError,
    AIMissingProviderConfigurationError,
    AIProviderTimeoutError,
)
from services.ai_provider.interface import AIProvider
from services.ai_provider.schemas import AIProviderChatResponse, AIUsage, ChatMessage

logger = logging.getLogger(__name__)


class AIChatResponse(BaseModel):
    model: str
    content: str
    finish_reason: str | None = None
    usage: AIUsage | None = None
    estimated_cost_usd: float | None = None
    latency_ms: float
    attempts: int


class AICostLimitExceededError(Exception):
    def __init__(self, *, estimated_cost_usd: float, max_cost_usd_per_run: float) -> None:
        super().__init__(
            f"Estimated AI cost (${estimated_cost_usd:.6f}) exceeds max allowed run cost "
            f"(${max_cost_usd_per_run:.6f})."
        )
        self.estimated_cost_usd = estimated_cost_usd
        self.max_cost_usd_per_run = max_cost_usd_per_run


def _estimate_cost_usd(
    *,
    usage: AIUsage | None,
    prompt_cost_usd_per_1k_tokens: float,
    completion_cost_usd_per_1k_tokens: float,
) -> float | None:
    if usage is None:
        return None
    if usage.prompt_tokens is None and usage.completion_tokens is None:
        return None

    prompt_tokens = usage.prompt_tokens or 0
    completion_tokens = usage.completion_tokens or 0
    cost = (prompt_tokens / 1000.0) * prompt_cost_usd_per_1k_tokens + (
        completion_tokens / 1000.0
    ) * completion_cost_usd_per_1k_tokens
    return cost


class AIService:
    def __init__(
        self,
        *,
        provider: AIProvider,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds_base: float,
        retry_backoff_seconds_max: float,
        prompt_cost_usd_per_1k_tokens: float,
        completion_cost_usd_per_1k_tokens: float,
        max_cost_usd_per_run: float | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds_base = retry_backoff_seconds_base
        self._retry_backoff_seconds_max = retry_backoff_seconds_max
        self._prompt_cost_usd_per_1k_tokens = prompt_cost_usd_per_1k_tokens
        self._completion_cost_usd_per_1k_tokens = completion_cost_usd_per_1k_tokens
        self._max_cost_usd_per_run = max_cost_usd_per_run

    async def chat(
        self,
        *,
        system_instruction: str | None,
        messages: Sequence[ChatMessage],
    ) -> AIChatResponse:
        attempts = 0
        last_error: AIProviderError | None = None

        # Note: latency_ms is measured for the actual API attempt (excluding
        # backoff sleep). Backoff time is still accounted for in overall run
        # time at the caller layer.
        for attempt in range(0, self._max_retries + 1):
            attempts = attempt + 1
            call_start = time.perf_counter()
            try:
                provider_result: AIProviderChatResponse = await asyncio.wait_for(
                    self._provider.chat(
                        model=self._model,
                        system_instruction=system_instruction,
                        messages=list(messages),
                    ),
                    timeout=self._timeout_seconds,
                )

                latency_ms = (time.perf_counter() - call_start) * 1000.0
                estimated_cost_usd = _estimate_cost_usd(
                    usage=provider_result.usage,
                    prompt_cost_usd_per_1k_tokens=self._prompt_cost_usd_per_1k_tokens,
                    completion_cost_usd_per_1k_tokens=self._completion_cost_usd_per_1k_tokens,
                )

                if (
                    self._max_cost_usd_per_run is not None
                    and estimated_cost_usd is not None
                    and estimated_cost_usd > self._max_cost_usd_per_run
                ):
                    raise AICostLimitExceededError(
                        estimated_cost_usd=estimated_cost_usd,
                        max_cost_usd_per_run=self._max_cost_usd_per_run,
                    )

                return AIChatResponse(
                    model=provider_result.model,
                    content=provider_result.content,
                    finish_reason=provider_result.finish_reason,
                    usage=provider_result.usage,
                    estimated_cost_usd=estimated_cost_usd,
                    latency_ms=latency_ms,
                    attempts=attempts,
                )
            except asyncio.TimeoutError:
                last_error = AIProviderTimeoutError("AI request timed out", retryable=True)

                if attempt >= self._max_retries:
                    logger.error("AI request failed after %s attempts: timeout", attempts)
                    raise last_error

                await self._sleep_before_retry(attempt=attempt, reason="timeout")
                continue
            except AIRateLimitError as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    logger.error(
                        "AI request failed after %s attempts: rate limit",
                        attempts,
                    )
                    raise

                await self._sleep_before_retry(attempt=attempt, reason="rate_limit")
                continue
            except AIProviderError as exc:
                last_error = exc
                if exc.retryable and attempt < self._max_retries:
                    await self._sleep_before_retry(attempt=attempt, reason="retryable_error")
                    continue

                logger.error(
                    "AI request failed on attempt %s (retryable=%s): %s",
                    attempts,
                    getattr(exc, "retryable", False),
                    type(exc).__name__,
                )
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("AIService.chat exited without result")

    async def _sleep_before_retry(self, *, attempt: int, reason: str) -> None:
        # Exponential backoff with jitter.
        exp = 2**attempt
        backoff = self._retry_backoff_seconds_base * exp
        jitter = random.uniform(0, self._retry_backoff_seconds_base)
        backoff_seconds = min(self._retry_backoff_seconds_max, backoff + jitter)

        logger.warning(
            "Retrying AI request (attempt=%s, reason=%s) after %.2fs",
            attempt + 1,
            reason,
            backoff_seconds,
        )
        await asyncio.sleep(backoff_seconds)


def _build_openai_provider(settings: Settings) -> AIProvider:
    # Imported lazily so importing the app doesn't import the OpenAI SDK.
    from services.ai_provider.openai_provider import OpenAIProvider

    return OpenAIProvider(
        api_key=settings.openai_api_key,
        client=None,
    )


def create_ai_service_from_settings(*, settings: Settings | None = None) -> AIService:
    """
    Construct an AIService configured for OpenAI.

    If OPENAI_API_KEY is missing, the application can still start; the
    provider will only fail when an actual AI request is made.
    """

    resolved = settings or get_settings()
    provider = _build_openai_provider(resolved)

    return AIService(
        provider=provider,
        model=resolved.openai_model,
        timeout_seconds=resolved.openai_timeout_seconds,
        max_retries=resolved.openai_max_retries,
        retry_backoff_seconds_base=resolved.openai_retry_backoff_seconds_base,
        retry_backoff_seconds_max=resolved.openai_retry_backoff_seconds_max,
        prompt_cost_usd_per_1k_tokens=resolved.openai_prompt_token_cost_usd_per_1k_tokens,
        completion_cost_usd_per_1k_tokens=resolved.openai_completion_token_cost_usd_per_1k_tokens,
        max_cost_usd_per_run=resolved.max_ai_cost_usd_per_run,
    )


__all__ = ["AIChatResponse", "AIService", "create_ai_service_from_settings"]

