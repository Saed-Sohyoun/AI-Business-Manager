"""Owner authentication — session cookie preferred; API key emergency/local only."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.exceptions import ForbiddenError, UnauthorizedError
from app.middleware.request_id import get_request_id
from app.models.base import utc_now
from app.owner.permissions import DEFAULT_OWNER_PERMISSIONS, has_owner_permission
from app.owner.session_auth import CSRF_HEADER, SESSION_COOKIE, SessionAuthService
from app.security import require_owner_identity


class OwnerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: str = Field(min_length=1, max_length=128)
    auth_method: str = "owner_api_key"
    permissions: frozenset[str] = Field(default_factory=lambda: DEFAULT_OWNER_PERMISSIONS)
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    csrf_token: str | None = None

    def require(self, permission: str) -> None:
        if not has_owner_permission(self.permissions, permission):
            raise ForbiddenError(
                "Owner permission denied",
                details={"permission": permission, "owner_id": self.owner_id},
            )


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def get_owner_context(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> OwnerContext:
    """Authenticate via session cookie (preferred) or emergency OWNER_API_KEY."""
    cfg = _settings(request)
    request_id = get_request_id(request) or str(uuid4())

    # 1) Session cookie
    raw = request.cookies.get(SESSION_COOKIE)
    auth = SessionAuthService(session, cfg)
    resolved = auth.resolve_session(raw)
    if resolved is not None:
        account, sess = resolved
        # CSRF for mutating methods
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            # Prefer header; also allow form field later
            auth.require_csrf(sess, request.headers.get(CSRF_HEADER))
            # Origin check when configured
            _validate_origin(request, cfg)
        return OwnerContext(
            owner_id=account.email,
            auth_method="session",
            permissions=DEFAULT_OWNER_PERMISSIONS,
            request_id=request_id,
            timestamp=utc_now(),
            csrf_token=sess.csrf_token,
        )

    # 2) Emergency / local API key (not for browser production UX)
    api_key = request.headers.get("X-Owner-API-Key")
    if api_key and cfg.owner_api_key_configured:
        try:
            owner_id = require_owner_identity(
                provided_api_key=api_key,
                settings=cfg,
                claimed_resolver=request.headers.get("X-Owner-Resolver") or "owner",
            )
        except UnauthorizedError:
            raise
        except ForbiddenError:
            raise
        return OwnerContext(
            owner_id=owner_id,
            auth_method="owner_api_key",
            permissions=DEFAULT_OWNER_PERMISSIONS,
            request_id=request_id,
            timestamp=utc_now(),
        )

    raise UnauthorizedError(
        "Authentication required",
        details={"code": "AUTH_REQUIRED", "hint": "Sign in or provide owner credentials"},
    )


def _validate_origin(request: Request, settings: Settings) -> None:
    origins = settings.cors_origin_list
    if not origins:
        return
    origin = request.headers.get("Origin")
    if origin and origin not in origins and "*" not in origins:
        raise ForbiddenError(
            "Cross-origin request blocked",
            details={"code": "FORBIDDEN", "reason": "origin"},
        )


OwnerDep = Annotated[OwnerContext, Depends(get_owner_context)]
