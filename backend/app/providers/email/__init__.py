"""Email provider package."""

from app.providers.email.base import EmailProvider
from app.providers.email.exceptions import (
    EmailConfigurationError,
    EmailError,
    EmailIdempotencyError,
    EmailMalformedResponseError,
    EmailProviderError,
    EmailRateLimitError,
    EmailTimeoutError,
    EmailValidationError,
)
from app.providers.email.recipient import normalize_and_validate_recipient
from app.providers.email.resend_provider import ResendEmailProvider
from app.providers.email.types import EmailAddress, EmailSendRequest, EmailSendResponse

__all__ = [
    "EmailAddress",
    "EmailConfigurationError",
    "EmailError",
    "EmailIdempotencyError",
    "EmailMalformedResponseError",
    "EmailProvider",
    "EmailProviderError",
    "EmailRateLimitError",
    "EmailSendRequest",
    "EmailSendResponse",
    "EmailTimeoutError",
    "EmailValidationError",
    "ResendEmailProvider",
    "normalize_and_validate_recipient",
]
