"""Rate-limit middleware for webhook and general API abuse protection."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings, get_settings
from app.middleware.request_id import get_request_id
from app.security.rate_limit import http_rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-client sliding window limits. Fail closed on excess."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cfg: Settings = getattr(request.app.state, "settings", None) or get_settings()
        client = request.client.host if request.client else "unknown"
        path = request.url.path

        if path.startswith(f"{cfg.api_prefix}/n8n"):
            limit = cfg.n8n_rate_limit_per_minute
            key = f"n8n:{client}"
        elif path == "/health":
            limit = cfg.health_rate_limit_per_minute
            key = f"health:{client}"
        else:
            limit = cfg.api_rate_limit_per_minute
            key = f"api:{client}:{path.split('/')[1] if path != '/' else 'root'}"

        if not http_rate_limiter.allow(key, limit=limit, window_seconds=60.0):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                        "details": {"retry_after_seconds": 60},
                        "request_id": get_request_id(request),
                    }
                },
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
