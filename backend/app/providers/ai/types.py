"""Normalized AI request/response types.

These types are provider-agnostic. Business logic and AIService depend on
these contracts, never on vendor SDK response objects.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AIMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class AICompletionRequest(BaseModel):
    """Provider-agnostic completion request."""

    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(min_length=1)
    system_instruction: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    # When json_schema is set, provider must return parseable JSON.
    json_schema: dict[str, Any] | None = None
    schema_name: str = "response"
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1.0)


class AIResponse(BaseModel):
    """Normalized AI completion result for observability and business use."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    structured_data: dict[str, Any] | None = None
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: Decimal = Decimal("0")
    latency_ms: float
    request_id: str | None = None
    provider: str = "openai"
    attempts: int = 1
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
