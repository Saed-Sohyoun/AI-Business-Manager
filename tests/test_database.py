from app.config import settings
from app.database import (
    check_database_connection,
    configured_dialect,
    dialect_from_url,
    get_engine,
    get_session_factory,
)


def test_dialect_from_url_reads_postgres_and_sqlite() -> None:
    assert (
        dialect_from_url("postgresql+psycopg://postgres:postgres@localhost:5432/ai_business_manager")
        == "postgresql"
    )
    assert dialect_from_url("sqlite:///:memory:") == "sqlite"
    assert dialect_from_url("") is None


def test_test_database_uses_sqlite() -> None:
    assert settings.environment == "test"
    assert settings.database_url.startswith("sqlite:///")
    assert configured_dialect() == "sqlite"
    assert get_engine().dialect.name == "sqlite"


def test_database_connection_check_succeeds() -> None:
    assert check_database_connection() is True


def test_session_factory_is_bound_to_engine() -> None:
    factory = get_session_factory()
    session = factory()
    try:
        assert session.bind is get_engine()
    finally:
        session.close()
