"""Normalized email request/response types."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DeliveryStatus = Literal[
    "accepted",
    "queued",
    "sent",
    "delivered",
    "bounced",
    "complained",
    "failed",
    "unknown",
]


class EmailAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    name: str | None = Field(default=None, max_length=255)


class EmailSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: EmailAddress
    subject: str = Field(min_length=1, max_length=300)
    body_text: str = Field(min_length=1, max_length=100_000)
    body_html: str | None = Field(default=None, max_length=200_000)
    from_email: str | None = Field(default=None, max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)
    idempotency_key: str = Field(min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1.0)


class EmailSendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    provider_message_id: str
    delivery_status: DeliveryStatus = "accepted"
    estimated_cost: Decimal = Decimal("0")
    latency_ms: float
    attempts: int = 1
    to_email: str
    subject: str
    metadata: dict[str, Any] = Field(default_factory=dict)
