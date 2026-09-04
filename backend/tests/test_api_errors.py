"""API error handling contract tests."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.exceptions import AppError, NotFoundError


def test_not_found_error_shape(app):
    router = APIRouter()

    @router.get("/_test/not-found")
    def trigger_not_found():
        raise NotFoundError("Lead not found", details={"lead_id": "abc"})

    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/_test/not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Lead not found"
    assert body["error"]["details"]["lead_id"] == "abc"
    assert body["error"]["request_id"]
    assert response.headers.get("X-Request-ID") == body["error"]["request_id"]


def test_unhandled_error_does_not_leak_internals(app):
    router = APIRouter()

    @router.get("/_test/boom")
    def trigger_boom():
        raise RuntimeError("secret internal detail")

    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret internal detail" not in body["error"]["message"]
    assert body["error"]["request_id"]


def test_http_exception_normalized(app):
    from fastapi import HTTPException

    router = APIRouter()

    @router.get("/_test/http")
    def trigger_http():
        raise HTTPException(status_code=400, detail="bad input")

    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/_test/http")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["message"] == "bad input"


def test_app_error_base_fields():
    err = AppError("x", code="custom", status_code=418, details={"a": 1})
    assert err.code == "custom"
    assert err.status_code == 418
    assert err.details == {"a": 1}
