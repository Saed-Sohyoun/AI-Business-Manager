from fastapi.testclient import TestClient

from app.exceptions import AppError


def test_unknown_route_does_not_become_500(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_unhandled_error_hides_internal_details(app) -> None:
    @app.get("/_test_error")
    def boom() -> None:
        raise RuntimeError("secret internals")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test_error")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "internal_error"
    assert "secret internals" not in response.text


def test_app_error_returns_structured_payload(app) -> None:
    @app.get("/_test_app_error")
    def fail() -> None:
        raise AppError("Lead is missing a website", code="missing_website")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test_app_error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "missing_website", "message": "Lead is missing a website"}
    }
