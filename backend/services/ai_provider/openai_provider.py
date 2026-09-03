from __future__ import annotations

import logging
import re
from typing import Any, Optional

from pydantic import SecretStr

from services.ai_provider.errors import (
    AIRateLimitError,
    AIMissingProviderConfigurationError,
    AIProviderError,
    AIProviderTimeoutError,
)
from services.ai_provider.interface import AIProvider
from services.ai_provider.schemas import AIProviderChatResponse, ChatMessage

logger = logging.getLogger(__name__)


def _redact_secrets(text: str) -> str:
    # Best-effort redaction for common OpenAI key prefixes (e.g. "sk-...").
    return re.sub(r"\bsk-[A-Za-z0-9]{10,}\b", "sk-[REDACTED]", text)


def _extract_status_code(exc: BaseException) -> int | None:
    # OpenAI exceptions often expose an HTTP status code either directly or
    # via an attached response object.
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    return None


class OpenAIProvider(AIProvider):
    """
    OpenAI-specific provider implementation.

    All OpenAI SDK imports and error mapping logic must live in this file.
    """

    def __init__(
        self,
        *,
        api_key: SecretStr | str,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key

        # Dependency injection for unit tests (mocked client).
        self._client = client
        if self._client is None:
            api_key_str = (
                api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
            )
            # Keep app startup safe: if the key is missing, defer the failure
            # until the first actual request.
            if api_key_str.strip():
                try:
                    from openai import AsyncOpenAI  # type: ignore
                except ImportError as exc:  # pragma: no cover
                    raise RuntimeError(
                        "OpenAI SDK is not installed. Add `openai` to dependencies."
                    ) from exc

                self._client = AsyncOpenAI(api_key=api_key_str)
            else:
                self._client = None

    async def chat(
        self,
        *,
        model: str,
        system_instruction: str | None,
        messages: list[ChatMessage],
    ) -> AIProviderChatResponse:
        api_key_str = (
            self._api_key.get_secret_value()
            if isinstance(self._api_key, SecretStr)
            else str(self._api_key)
        )
        if not api_key_str.strip():
            raise AIMissingProviderConfigurationError(
                "Missing OpenAI API key. Configure `OPENAI_API_KEY`."
            )
        if self._client is None:  # pragma: no cover (covered by missing-key test)
            raise AIMissingProviderConfigurationError(
                "OpenAI client is not configured. Check `OPENAI_API_KEY`."
            )

        openai_messages: list[dict[str, str]] = []
        if system_instruction and system_instruction.strip():
            openai_messages.append({"role": "system", "content": system_instruction.strip()})
        for msg in messages:
            openai_messages.append({"role": msg.role, "content": msg.content})

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=openai_messages,
            )
        except Exception as exc:  # noqa: BLE001
            status_code = _extract_status_code(exc)

            # Best-effort classification for retry behavior.
            if status_code == 429:
                raise AIRateLimitError("OpenAI rate limit exceeded") from None

            if status_code in {408, 500, 502, 503, 504}:
                raise AIProviderError(
                    "OpenAI temporary error",
                    retryable=True,
                ) from None

            # Some SDKs raise timeout exceptions; AIService already handles
            # timeouts via asyncio.wait_for, but this keeps it safe.
            exc_name = type(exc).__name__.lower()
            if "timeout" in exc_name:
                raise AIProviderTimeoutError("OpenAI request timed out") from None

            msg = _redact_secrets(str(exc))
            logger.error(
                "OpenAI request failed: %s (status_code=%s)",
                msg[:300],
                status_code,
            )
            raise AIProviderError("OpenAI request failed") from None

        choice0 = response.choices[0]
        content: str = getattr(getattr(choice0, "message", None), "content", None) or ""
        finish_reason: Optional[str] = getattr(choice0, "finish_reason", None)

        usage_obj = getattr(response, "usage", None)
        usage = None
        if usage_obj is not None:
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
                "completion_tokens": getattr(usage_obj, "completion_tokens", None),
                "total_tokens": getattr(usage_obj, "total_tokens", None),
            }

        return AIProviderChatResponse(
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            model=model,
        )

