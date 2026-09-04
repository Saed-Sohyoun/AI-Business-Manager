"""Health endpoint tests."""

from __future__ import annotations


def test_health_returns_ok_structure(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["service"]
    assert body["version"]
    assert body["environment"] == "test"
    assert body["database"] in {"ok", "unavailable"}
    assert "request_id" in body


def test_health_includes_request_id_header(client):
    response = client.get("/health", headers={"X-Request-ID": "test-correlation-1"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-correlation-1"
    assert response.json()["request_id"] == "test-correlation-1"


def test_health_generates_request_id_when_missing(client):
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert response.json()["request_id"] == request_id


def test_health_degraded_when_database_unavailable(monkeypatch):
    from app.api import health as health_module
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    cfg = Settings(
        app_env="test",
        database_url="postgresql+psycopg://invalid:invalid@127.0.0.1:1/none",
        database_connect_timeout=1,
        cors_origins="",
    )
    monkeypatch.setattr(health_module, "_check_database", lambda _s: "unavailable")
    application = create_app(cfg)
    with TestClient(application) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"