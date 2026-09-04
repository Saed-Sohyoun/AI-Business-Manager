"""Owner session authentication — cookie + CSRF; API key remains emergency fallback."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import ForbiddenError, UnauthorizedError, ValidationAppError
from app.models.base import utc_now
from app.models.owner_account import OwnerAccount
from app.models.owner_session import OwnerSession
from app.security.passwords import hash_password, verify_password
from app.security.rate_limit import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)

SESSION_COOKIE = "bos_owner_session"
CSRF_HEADER = "X-CSRF-Token"
LOGIN_LIMITER = SlidingWindowRateLimiter()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SessionAuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def ensure_bootstrap_owner(self) -> OwnerAccount | None:
        """Create bootstrap owner from env when table empty (dev/test only)."""
        existing = self._session.scalar(select(OwnerAccount).limit(1))
        if existing is not None:
            return existing
        email = (self._settings.owner_bootstrap_email or "").strip().lower()
        password = self._settings.owner_bootstrap_password
        if not email or not password:
            return None
        pwd = password.get_secret_value() if hasattr(password, "get_secret_value") else str(password)
        if not pwd.strip():
            return None
        row = OwnerAccount(
            email=email,
            password_hash=hash_password(pwd.strip()),
            display_name="Owner",
            active=True,
        )
        self._session.add(row)
        self._session.commit()
        logger.info("bootstrap_owner_created email=%s", email)
        return row

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        ip_hint: str | None,
    ) -> tuple[OwnerSession, str]:
        """Return (session_row, raw_token). Rate-limited by IP hint."""
        key = f"login:{(ip_hint or 'unknown')}"
        allowed = LOGIN_LIMITER.allow(
            key,
            limit=self._settings.owner_login_rate_limit_per_minute,
            window_seconds=60,
        )
        if not allowed:
            raise ForbiddenError(
                "Too many login attempts. Try again shortly.",
                details={"code": "RATE_LIMITED"},
            )

        self.ensure_bootstrap_owner()
        account = self._session.scalar(
            select(OwnerAccount).where(OwnerAccount.email == email.strip().lower())
        )
        if account is None or not account.active:
            raise UnauthorizedError("Invalid email or password")
        if not verify_password(password, account.password_hash):
            raise UnauthorizedError("Invalid email or password")

        raw = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        hours = self._settings.owner_session_ttl_hours
        row = OwnerSession(
            owner_id=account.id,
            token_hash=_hash_token(raw),
            csrf_token=csrf,
            expires_at=utc_now() + timedelta(hours=hours),
            user_agent=(user_agent or "")[:255] or None,
            ip_hint=(ip_hint or "")[:64] or None,
        )
        account.last_login_at = utc_now()
        self._session.add(row)
        self._session.commit()
        return row, raw

    def resolve_session(self, raw_token: str | None) -> tuple[OwnerAccount, OwnerSession] | None:
        if not raw_token or not raw_token.strip():
            return None
        token_hash = _hash_token(raw_token.strip())
        sess = self._session.scalar(
            select(OwnerSession).where(OwnerSession.token_hash == token_hash)
        )
        if sess is None or not sess.is_valid:
            return None
        account = self._session.get(OwnerAccount, sess.owner_id)
        if account is None or not account.active:
            return None
        return account, sess

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token_hash = _hash_token(raw_token.strip())
        sess = self._session.scalar(
            select(OwnerSession).where(OwnerSession.token_hash == token_hash)
        )
        if sess is None:
            return
        sess.revoked_at = utc_now()
        self._session.commit()

    def require_csrf(self, sess: OwnerSession, provided: str | None) -> None:
        if not provided or not hmac.compare_digest(provided.strip(), sess.csrf_token):
            raise ForbiddenError(
                "CSRF validation failed",
                details={"code": "FORBIDDEN", "reason": "csrf"},
            )


def create_owner_account(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: str = "Owner",
) -> OwnerAccount:
    if len(password) < 10:
        raise ValidationAppError("Password must be at least 10 characters")
    row = OwnerAccount(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        active=True,
    )
    session.add(row)
    session.commit()
    return row
