"""NotificationProvider port — business code depends on this interface only."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.notification.types import NotificationSendRequest, NotificationSendResponse


class NotificationProvider(ABC):
    """Abstract notification send provider."""

    name: str = "notification"

    @abstractmethod
    def send(self, request: NotificationSendRequest) -> NotificationSendResponse:
        """Send a single notification and return a normalized response."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has enough config to attempt a call."""
