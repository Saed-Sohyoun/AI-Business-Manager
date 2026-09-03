from fastapi.testclient import TestClient


def test_health_returns_ok_with_sqlite(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "AI Business Manager"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "test"
    assert payload["database"]["configured"] is True
    assert payload["database"]["connected"] is True
    assert payload["database"]["dialect"] == "sqlite"


def test_health_includes_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "phase1-health"})
    assert response.headers["X-Request-ID"] == "phase1-health"
