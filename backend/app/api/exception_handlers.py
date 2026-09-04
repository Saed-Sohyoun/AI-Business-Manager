"""Centralized FastAPI exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import AppError
from app.middleware.request_id import get_request_id
from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Make Pydantic/FastAPI validation error payloads JSON-serializable."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, BaseException):
        return str(value)
    return str(value)


def _error_body(
    *,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            request_id=request_id,
        )
    )
    return payload.model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = get_request_id(request)
        logger.warning(
            "Application error code=%s message=%s",
            exc.code,
            exc.message,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = get_request_id(request)
        return JSONResponse(
            status_code=422,
            content=_error_body(
                code="validation_error",
                message="Request validation failed",
                request_id=request_id,
                details={"errors": _json_safe(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        request_id = get_request_id(request)
        detail = exc.detail
        message = detail if isinstance(detail, str) else "HTTP error"
        details: dict[str, Any] = {}
        if isinstance(detail, dict):
            details = detail
            message = str(detail.get("message", message))
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                code="http_error",
                message=message,
                request_id=request_id,
                details=details,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.exception(
            "Unhandled exception: %s",
            exc,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=500,
            content=_error_body(
                code="internal_error",
                message="An unexpected error occurred",
                request_id=request_id,
            ),
        )
