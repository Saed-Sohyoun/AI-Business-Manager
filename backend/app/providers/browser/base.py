"""BrowserProvider port — business code depends on this interface only."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.browser.types import BrowserFetchRequest, BrowserPageSnapshot


class BrowserProvider(ABC):
    """Abstract controlled browser capability.

    Implementations must not expose shell access, arbitrary code execution,
    downloads, or credential handling. All page content is untrusted.
    """

    name: str = "browser"

    @abstractmethod
    def fetch(self, request: BrowserFetchRequest) -> BrowserPageSnapshot:
        """Open a URL and return a bounded, untrusted page snapshot."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider can attempt a fetch."""
