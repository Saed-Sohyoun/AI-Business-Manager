"""AIService — application-facing AI operations over AIProvider.

Business logic should inject/use AIService (or AIProvider), never the OpenAI SDK.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.providers.ai.base import AIProvider
from app.providers.ai.exceptions import AIMalformedResponseError
from app.providers.ai.openai_provider import OpenAIProvider
from app.providers.ai.types import AICompletionRequest, AIResponse

T = TypeVar("T", bound=BaseModel)


class AIService:
    """High-level AI operations with structured-output helpers."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> AIProvider:
        return self._provider

    def is_configured(self) -> bool:
        return self._provider.is_configured()

    def complete(
        self,
        *,
        user_message: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.2,
        max_output_tokens: int | None = None,
        metadata: dict | None = None,
        timeout_seconds: float | None = None,
    ) -> AIResponse:
        request = AICompletionRequest(
            user_message=user_message,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata=metadata or {},
            timeout_seconds=timeout_seconds,
        )
        return self._provider.complete(request)

    def complete_structured(
        self,
        *,
        user_message: str,
        response_model: type[T],
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.2,
        max_output_tokens: int | None = None,
        metadata: dict | None = None,
        timeout_seconds: float | None = None,
        schema_name: str | None = None,
    ) -> tuple[AIResponse, T]:
        """Complete with JSON schema and validate into a Pydantic model."""
        schema = response_model.model_json_schema()
        request = AICompletionRequest(
            user_message=user_message,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            json_schema=schema,
            schema_name=schema_name or response_model.__name__,
            metadata=metadata or {},
            timeout_seconds=timeout_seconds,
        )
        response = self._provider.complete(request)
        if not response.structured_data:
            raise AIMalformedResponseError(
                "AI structured response contained no data",
                details={"model": response_model.__name__},
            )
        try:
            parsed = response_model.model_validate(response.structured_data)
        except ValidationError as exc:
            raise AIMalformedResponseError(
                "AI structured response failed schema validation",
                details={"model": response_model.__name__, "errors": exc.errors()},
            ) from exc
        return response, parsed


def build_openai_provider(settings: Settings | None = None) -> OpenAIProvider:
    return OpenAIProvider(settings or get_settings())


def build_ai_service(
    settings: Settings | None = None,
    *,
    provider: AIProvider | None = None,
) -> AIService:
    """Factory used by future agents/services — does not require API key at build time."""
    cfg = settings or get_settings()
    return AIService(provider or build_openai_provider(cfg))
