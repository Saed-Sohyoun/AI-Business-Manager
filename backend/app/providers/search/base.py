"""SearchProvider port — business code depends on this interface only."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.search.types import SearchRequest, SearchResponse


class SearchProvider(ABC):
    """Abstract web search provider.

    Implementations may call vendor APIs. Callers must never import those clients.
    All returned content is untrusted external data.
    """

    name: str = "search"

    @abstractmethod
    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a web search and return normalized, validated results."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has enough config to attempt a call."""
