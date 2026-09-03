from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from services.ai_provider.errors import AIProviderError
from services.ai_provider.schemas import AIProviderChatResponse, ChatMessage


class AIProvider(Protocol):
    async def chat(
        self,
        *,
        model: str,
        system_instruction: str | None,
        messages: Sequence[ChatMessage],
    ) -> AIProviderChatResponse:
        """
        Create a chat completion.

        Providers must raise AIProviderError subclasses on failure (never
        vendor exceptions leaking through to AIService).
        """

        raise AIProviderError("Not implemented")

