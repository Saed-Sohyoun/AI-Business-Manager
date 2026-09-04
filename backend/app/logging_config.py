"""Structured logging configuration.

Never log secrets. Database URLs and API keys must be redacted by callers
before being passed into log records.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.config import Settings


class RequestIdFilter(logging.Filter):
    """Inject request_id into log records when present in context."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging(settings: Settings) -> None:
    """Configure root and app loggers for structured, readable output."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.log_level)
    handler.addFilter(RequestIdFilter())

    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)s | %(name)s | "
            "request_id=%(request_id)s | %(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Keep noisy third-party loggers under control
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.database_echo else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the application namespace."""
    return logging.getLogger(name)


def bind_request_id(logger: logging.Logger, request_id: str) -> logging.LoggerAdapter[Any]:
    """Return a logger adapter that always includes request_id."""
    return logging.LoggerAdapter(logger, {"request_id": request_id})
