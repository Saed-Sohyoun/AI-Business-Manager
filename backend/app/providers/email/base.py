"""EmailProvider port — business code depends on this interface only."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.email.types import EmailSendRequest, EmailSendResponse


class EmailProvider(ABC):
    """Abstract email send provider.

    Implementations may wrap vendor APIs. Callers must never import those SDKs.
    """

    name: str = "email"

    @abstractmethod
    def send(self, request: EmailSendRequest) -> EmailSendResponse:
        """Send a single email and return a normalized response."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has enough config to attempt a call."""
