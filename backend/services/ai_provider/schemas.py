from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class AIUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class AIProviderChatResponse(BaseModel):
    """
    Provider-level chat result (token usage, finish reason, etc.).

    AIService wraps this with latency measurement, retries, cost estimation,
    and error normalization.
    """

    content: str
    finish_reason: Optional[str] = None
    usage: Optional[AIUsage] = None
    model: str

