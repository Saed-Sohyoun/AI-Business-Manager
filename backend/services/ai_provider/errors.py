from __future__ import annotations


class AIProviderError(Exception):
    """
    Base error raised by AI providers.

    Providers should map vendor-specific errors (e.g. OpenAI 429) into the
    generic subclasses below. AIService is responsible for retries, timeout
    behavior, and cost/latency bookkeeping.
    """

    retryable: bool = False

    def __init__(self, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable if retryable is not None else type(self).retryable


class AIMissingProviderConfigurationError(AIProviderError):
    retryable = False


class AIRateLimitError(AIProviderError):
    retryable = True


class AITemporaryProviderError(AIProviderError):
    retryable = True


class AIProviderTimeoutError(AIProviderError):
    retryable = True

