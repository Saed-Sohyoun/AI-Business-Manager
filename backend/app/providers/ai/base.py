"""AIProvider port — business code depends on this interface only."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.ai.types import AICompletionRequest, AIResponse


class AIProvider(ABC):
    """Abstract AI completion provider.

    Implementations may wrap vendor SDKs. Callers must never import those SDKs.
    """

    name: str = "ai"

    @abstractmethod
    def complete(self, request: AICompletionRequest) -> AIResponse:
        """Execute a completion request and return a normalized response."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has enough config to attempt a call."""
