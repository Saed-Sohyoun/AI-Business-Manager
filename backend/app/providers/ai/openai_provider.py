"""OpenAI adapter implementing AIProvider.

This is the only module that may import the OpenAI SDK.
Business logic must depend on AIProvider / AIService instead.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any

from app.config import Settings
from app.providers.ai.base import AIProvider
from app.providers.ai.costing import estimate_cost_usd, total_tokens
from app.providers.ai.exceptions import (
    AIConfigurationError,
    AIMalformedResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from app.providers.ai.safe_logging import (
    log_completion_failed,
    log_completion_started,
    log_completion_succeeded,
)
from app.providers.ai.schema_utils import prepare_openai_strict_schema
from app.providers.ai.types import AICompletionRequest, AIResponse


def _retry_after_seconds(exc: BaseException, attempt: int) -> float:
    """Compute backoff delay; prefer provider Retry-After when available."""
    header_value: str | None = None
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        header_value = headers.get("retry-after") or headers.get("Retry-After")
    if header_value:
        try:
            return max(float(header_value), 0.1)
        except ValueError:
            pass
    # Exponential backoff with jitter
    base = min(2**attempt, 20)
    return base + random.uniform(0, 0.25)


class OpenAIProvider(AIProvider):
    """OpenAI Chat Completions adapter with retries and normalized errors."""

    name = "openai"

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        sleep_fn: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._sleep = sleep_fn or time.sleep

    def is_configured(self) -> bool:
        return self._settings.openai_configured

    def complete(self, request: AICompletionRequest) -> AIResponse:
        model = request.model or self._settings.openai_model
        max_retries = self._settings.openai_max_retries
        timeout = request.timeout_seconds or self._settings.openai_timeout

        client = self._ensure_client(timeout=timeout)
        messages = self._build_messages(request)
        create_kwargs = self._build_create_kwargs(
            model=model,
            messages=messages,
            request=request,
            timeout=timeout,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= max_retries:
            attempts += 1
            log_completion_started(
                provider=self.name,
                model=model,
                request=request,
                attempt=attempts,
            )
            started = time.perf_counter()
            try:
                raw = client.chat.completions.create(**create_kwargs)
                latency_ms = (time.perf_counter() - started) * 1000
                response = self._normalize_response(
                    raw=raw,
                    model=model,
                    latency_ms=latency_ms,
                    attempts=attempts,
                    request=request,
                )
                log_completion_succeeded(response=response)
                return response
            except AIConfigurationError:
                raise
            except Exception as exc:  # noqa: BLE001 — mapped to typed AI errors
                last_error = exc
                mapped = self._map_exception(exc)
                log_completion_failed(
                    provider=self.name,
                    model=model,
                    attempt=attempts,
                    error_code=mapped.code,
                    error_type=type(exc).__name__,
                    metadata=request.metadata,
                )
                retryable = isinstance(mapped, (AITimeoutError, AIRateLimitError)) or (
                    isinstance(mapped, AIProviderError)
                    and mapped.details.get("retryable") is True
                )
                if not retryable or attempts > max_retries:
                    raise mapped from exc
                self._sleep(_retry_after_seconds(exc, attempts))

        # Defensive — loop should always raise or return
        raise AIProviderError(
            "AI provider request failed after retries",
            details={"attempts": attempts, "reason": str(last_error) if last_error else None},
        )

    def _ensure_client(self, *, timeout: float) -> Any:
        if not self.is_configured():
            raise AIConfigurationError(
                "OPENAI_API_KEY is not configured. Set it in the environment to use AI features.",
                details={"provider": self.name},
            )
        if self._client is not None:
            return self._client

        # Lazy import — keeps startup free of SDK side effects when unused
        from openai import OpenAI

        api_key = self._settings.openai_api_key
        assert api_key is not None  # guarded by is_configured
        self._client = OpenAI(
            api_key=api_key.get_secret_value(),
            timeout=timeout,
            max_retries=0,  # retries owned by this adapter for observability
        )
        return self._client

    @staticmethod
    def _build_messages(request: AICompletionRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.append({"role": "user", "content": request.user_message})
        return messages

    @staticmethod
    def _build_create_kwargs(
        *,
        model: str,
        messages: list[dict[str, str]],
        request: AICompletionRequest,
        timeout: float,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens
        if request.json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "schema": prepare_openai_strict_schema(request.json_schema),
                    "strict": True,
                },
            }
        return kwargs

    def _normalize_response(
        self,
        *,
        raw: Any,
        model: str,
        latency_ms: float,
        attempts: int,
        request: AICompletionRequest,
    ) -> AIResponse:
        try:
            choice = raw.choices[0]
            message = choice.message
            content = getattr(message, "content", None)
            finish_reason = getattr(choice, "finish_reason", None)
        except (AttributeError, IndexError, TypeError) as exc:
            raise AIMalformedResponseError(
                "AI provider response missing choices/message",
                details={"provider": self.name},
            ) from exc

        usage = getattr(raw, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        provider_request_id = getattr(raw, "id", None)

        structured: dict[str, Any] | None = None
        if request.json_schema is not None:
            if not content or not str(content).strip():
                raise AIMalformedResponseError(
                    "Structured AI response was empty",
                    details={"provider": self.name},
                )
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise AIMalformedResponseError(
                    "Structured AI response was not valid JSON",
                    details={"provider": self.name},
                ) from exc
            if not isinstance(parsed, dict):
                raise AIMalformedResponseError(
                    "Structured AI response JSON must be an object",
                    details={"provider": self.name},
                )
            structured = parsed

        resolved_model = getattr(raw, "model", None) or model
        return AIResponse(
            content=content,
            structured_data=structured,
            model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens(input_tokens, output_tokens),
            estimated_cost=estimate_cost_usd(
                model=resolved_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
            latency_ms=latency_ms,
            request_id=provider_request_id,
            provider=self.name,
            attempts=attempts,
            finish_reason=finish_reason,
            metadata=dict(request.metadata),
        )

    def _map_exception(self, exc: Exception) -> Exception:
        # Import locally so missing optional SDK types don't break module import
        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                AuthenticationError,
                BadRequestError,
                RateLimitError,
            )
        except ImportError:
            return AIProviderError(
                "OpenAI SDK is not installed",
                details={"provider": self.name, "retryable": False},
            )

        if isinstance(exc, (AIConfigurationError, AITimeoutError, AIRateLimitError, AIProviderError, AIMalformedResponseError)):
            return exc
        if isinstance(exc, APITimeoutError):
            return AITimeoutError(
                "OpenAI request timed out",
                details={"provider": self.name, "retryable": True},
            )
        if isinstance(exc, RateLimitError):
            return AIRateLimitError(
                "OpenAI rate limit exceeded",
                details={"provider": self.name, "retryable": True},
            )
        if isinstance(exc, AuthenticationError):
            return AIConfigurationError(
                "OpenAI authentication failed — check OPENAI_API_KEY",
                details={"provider": self.name},
            )
        if isinstance(exc, BadRequestError):
            return AIProviderError(
                "OpenAI rejected the request",
                details={"provider": self.name, "retryable": False},
            )
        if isinstance(exc, APIConnectionError):
            return AIProviderError(
                "Failed to connect to OpenAI",
                details={"provider": self.name, "retryable": True},
            )
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            retryable = bool(status and int(status) >= 500)
            return AIProviderError(
                "OpenAI returned an error response",
                details={
                    "provider": self.name,
                    "status_code": status,
                    "retryable": retryable,
                },
            )
        return AIProviderError(
            "Unexpected AI provider failure",
            details={"provider": self.name, "error_type": type(exc).__name__, "retryable": False},
        )
