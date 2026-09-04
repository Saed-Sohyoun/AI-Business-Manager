"""SQLAlchemy 2 engine and session management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine from settings."""
    cfg = settings or get_settings()
    url = cfg.database_url

    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {
        "echo": cfg.database_echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if _is_sqlite(url):
        # SQLite is used for automated tests only in Phase 1.
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
        # :memory: DBs are per-connection unless StaticPool shares one connection.
        if ":memory:" in url:
            engine_kwargs["poolclass"] = StaticPool
    else:
        # psycopg connect_timeout keeps health/readiness checks from hanging
        connect_args["connect_timeout"] = cfg.database_connect_timeout
        engine_kwargs["connect_args"] = connect_args
        engine_kwargs.update(
            {
                "pool_size": cfg.database_pool_size,
                "max_overflow": cfg.database_max_overflow,
                "pool_timeout": cfg.database_pool_timeout,
            }
        )

    engine = create_engine(url, **engine_kwargs)

    if _is_sqlite(url):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(settings: Settings | None = None, *, force: bool = False) -> Engine:
    """Initialize global engine and session factory.

    Reuses an existing engine unless ``force=True``, so FastAPI lifespan does not
    replace a test-initialized ``:memory:`` SQLite connection (and wipe schema).
    """
    global _engine, _SessionLocal

    if _engine is not None and not force:
        return _engine

    if _engine is not None and force:
        previous = _engine
        _engine = None
        _SessionLocal = None
        previous.dispose()

    cfg = settings or get_settings()
    _engine = create_db_engine(cfg)
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_db()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def reset_db_state() -> None:
    """Dispose global engine/session state (tests and orderly process shutdown)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
