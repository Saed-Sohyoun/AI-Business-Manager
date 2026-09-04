"""Provider error classification for resilience."""

from __future__ import annotations

from enum import Enum


class ProviderErrorClass(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    UPSTREAM_4XX = "UPSTREAM_4XX"
    UPSTREAM_5XX = "UPSTREAM_5XX"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


def should_retry(error_class: ProviderErrorClass) -> bool:
    return error_class in {
        ProviderErrorClass.RATE_LIMIT,
        ProviderErrorClass.TIMEOUT,
        ProviderErrorClass.NETWORK_ERROR,
        ProviderErrorClass.UPSTREAM_5XX,
    }
