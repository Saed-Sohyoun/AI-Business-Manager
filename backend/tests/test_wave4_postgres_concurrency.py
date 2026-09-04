"""Optional Postgres concurrency checks — skipped without POSTGRES_TEST_URL."""

from __future__ import annotations

import os

import pytest

POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set POSTGRES_TEST_URL to run Postgres concurrency tests",
)


@pytest.fixture()
def pg_settings(settings):
    from pydantic import SecretStr

    return settings.model_copy(
        update={
            "database_url": POSTGRES_URL,
            "owner_api_key": SecretStr("pg-owner-key"),
            "approval_authorized_resolvers": "owner,admin",
        }
    )


def test_idempotent_command_under_concurrency(pg_settings):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from unittest.mock import patch

    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.config import clear_settings_cache
    from app.database import init_db, reset_db_state
    from app.main import create_app
    from app.models import Base

    clear_settings_cache()
    reset_db_state()
    app = create_app(pg_settings)
    engine = init_db(pg_settings, force=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    headers = {"X-Owner-API-Key": "pg-owner-key", "X-Owner-Resolver": "owner"}
    body = {
        "niche": "cafes",
        "location": "Berlin",
        "desired_count": 1,
        "idempotency_key": "pg-idem-concurrent-001",
    }

    with TestClient(app) as client:
        with patch("app.owner.commands.OwnerCommandService._spawn_find_opportunities"):

            def once():
                return client.post(
                    "/api/v1/owner/commands/find-opportunities",
                    headers=headers,
                    json=body,
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(as_completed([pool.submit(once) for _ in range(8)]))
            statuses = [f.result().status_code for f in results]
            ids = {
                f.result().json()["data"]["execution_id"]
                for f in results
                if f.result().status_code == 202
            }
    assert all(s == 202 for s in statuses)
    assert len(ids) == 1
    reset_db_state()
    clear_settings_cache()
