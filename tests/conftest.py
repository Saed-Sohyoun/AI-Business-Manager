import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_engine, reset_engine
from app.main import create_app
from models.base import Base

get_settings.cache_clear()
reset_engine()


@pytest.fixture
def app() -> Generator[FastAPI, None, None]:
    reset_engine()
    engine = get_engine()
    Base.metadata.create_all(engine)
    application = create_app()
    yield application
    Base.metadata.drop_all(engine)
    reset_engine()


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
