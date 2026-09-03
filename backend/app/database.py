import threading
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from models.base import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        kwargs: dict = {
            "connect_args": {"check_same_thread": False},
        }
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
        return kwargs
    return {
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": 3},
    }


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            future=True,
            **_engine_kwargs(settings.database_url),
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def dialect_from_url(database_url: str) -> str | None:
    if not database_url.strip():
        return None
    return database_url.split("://", 1)[0].split("+", 1)[0]


def configured_dialect() -> str | None:
    if not settings.database_is_configured():
        return None
    return dialect_from_url(settings.database_url)


def check_database_connection(timeout_seconds: float = 3.0) -> bool:
    result = {"ok": False}

    def _check() -> None:
        try:
            engine = get_engine()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            result["ok"] = True
        except Exception:
            result["ok"] = False

    worker = threading.Thread(target=_check, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        return False
    return result["ok"]


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


__all__ = [
    "Base",
    "check_database_connection",
    "configured_dialect",
    "dialect_from_url",
    "get_db",
    "get_engine",
    "get_session_factory",
    "reset_engine",
]
