"""External provider ports and adapters.

Business logic depends on interfaces in this package, not vendor SDKs.
"""

from app.providers.ai import AIProvider, AIResponse, OpenAIProvider
from app.providers.browser import BrowserProvider, BrowserPageSnapshot, PlaywrightBrowserProvider
from app.providers.email import EmailProvider, EmailSendResponse, ResendEmailProvider
from app.providers.notification import (
    NotificationProvider,
    NotificationSendResponse,
    TelegramProvider,
)
from app.providers.search import SearchProvider, SearchResponse, TavilySearchProvider

__all__ = [
    "AIProvider",
    "AIResponse",
    "BrowserPageSnapshot",
    "BrowserProvider",
    "EmailProvider",
    "EmailSendResponse",
    "NotificationProvider",
    "NotificationSendResponse",
    "OpenAIProvider",
    "PlaywrightBrowserProvider",
    "ResendEmailProvider",
    "SearchProvider",
    "SearchResponse",
    "TelegramProvider",
    "TavilySearchProvider",
]
