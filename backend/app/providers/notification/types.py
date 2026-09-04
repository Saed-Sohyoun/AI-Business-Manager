"""Normalized notification request/response types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import NotificationCategory, NotificationPriority


class NotificationSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    priority: NotificationPriority = NotificationPriority.IMPORTANT
    category: NotificationCategory = NotificationCategory.OTHER
    idempotency_key: str = Field(min_length=1, max_length=128)
    chat_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1.0)


class NotificationSendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    provider_message_id: str
    latency_ms: float
    attempts: int = 1
    priority: NotificationPriority
    category: NotificationCategory
    metadata: dict[str, Any] = Field(default_factory=dict)
