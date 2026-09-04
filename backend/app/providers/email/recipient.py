"""Email recipient validation."""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from app.providers.email.exceptions import EmailValidationError
from app.providers.email.types import EmailAddress


def normalize_and_validate_recipient(email: str, *, name: str | None = None) -> EmailAddress:
    """Validate and normalize a recipient address. Rejects invalid/empty values."""
    raw = (email or "").strip()
    if not raw:
        raise EmailValidationError("Recipient email is required", details={"field": "to"})
    try:
        result = validate_email(raw, check_deliverability=False)
    except EmailNotValidError as exc:
        raise EmailValidationError(
            "Invalid recipient email",
            details={"email": raw, "reason": str(exc)},
        ) from exc

    normalized = result.normalized
    # Block obvious role/spam traps only lightly — no mass send
    local = normalized.split("@", 1)[0].lower()
    if local in {"noreply", "no-reply", "mailer-daemon"}:
        raise EmailValidationError(
            "Recipient address is not allowed for outbound sales email",
            details={"email": normalized},
        )
    clean_name = name.strip() if name and name.strip() else None
    return EmailAddress(email=normalized, name=clean_name)


def normalize_from_address(email: str) -> str:
    raw = (email or "").strip()
    if not raw:
        raise EmailValidationError("EMAIL_FROM is required", details={"field": "from"})
    try:
        result = validate_email(raw, check_deliverability=False)
    except EmailNotValidError as exc:
        raise EmailValidationError(
            "Invalid EMAIL_FROM address",
            details={"email": raw, "reason": str(exc)},
        ) from exc
    return result.normalized
