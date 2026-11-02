"""NFR-01 / SEC-08 / SEC-10: consistent error envelope, no internals, body limits, headers, CORS."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from tests.conftest import Actor


def test_error_envelope_and_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/datasets", headers={"X-Request-ID": "trace-12345678"})
    body = response.json()
    assert response.status_code == 401 and set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["request_id"] == "trace-12345678" == response.headers["x-request-id"]
    assert client.get("/api/v1/does-not-exist").json()["error"]["code"] == "not_found"
    invalid_id = client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces"})
    assert invalid_id.headers["x-request-id"] != "bad id with spaces"


def test_unhandled_errors_do_not_leak_internals(app, actors: dict[str, Actor]) -> None:  # type: ignore[no-untyped-def]
    router = APIRouter()

    @router.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("secret connection string postgresql://user:pass@db/x")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/_boom")
    assert response.status_code == 500
    text = response.text
    assert "postgresql://" not in text and "Traceback" not in text and "RuntimeError" not in text
    assert response.json()["error"]["code"] == "internal_error"


def test_validation_errors_are_400_and_do_not_echo_input(client: TestClient, actors: dict[str, Actor]) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "<script>@x", "password": "secret-value-123"})
    assert response.status_code == 400
    assert "secret-value-123" not in response.text and response.json()["error"]["code"] == "validation_error"


def test_json_body_size_limit(client: TestClient, actors: dict[str, Actor], settings) -> None:  # type: ignore[no-untyped-def]
    huge = b'{"email": "a@example.org", "password": "' + b"x" * (settings.max_json_body_bytes + 10) + b'"}'
    response = client.post("/api/v1/auth/login", content=huge, headers={"Content-Type": "application/json"})
    assert response.status_code == 413 and response.json()["error"]["code"] == "payload_too_large"


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/api/v1/health").headers
    assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"].startswith("default-src 'none'") and headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"


def test_cors_allowlist(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/auth/login", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    denied = client.options(
        "/api/v1/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in denied.headers


def test_health_does_not_disclose_internals(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] in {"ok", "degraded"} and set(body["checks"]) == {"database", "model_registry", "job_runner"}
    assert "sqlite" not in str(body) and "/" not in "".join(body["checks"].values())
