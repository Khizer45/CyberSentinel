"""FR-01 / SEC-01 / SEC-10: login, refresh rotation, logout revocation, lockout, password change, rate limits."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import Database
from app.models import AuditLog, User
from tests.conftest import PASSWORD, Actor

LOGIN = "/api/v1/auth/login"


def login(client: TestClient, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post(LOGIN, json={"email": email, "password": password})


def test_login_success_sets_httponly_scoped_cookie(client: TestClient, actors: dict[str, Actor]) -> None:
    response = login(client, "ANALYST@example.org")  # e-mail is case-normalized
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "analyst"
    assert "password_hash" not in body["user"]
    cookie = response.headers["set-cookie"]
    assert "cs_refresh=" in cookie and "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie and "SameSite=strict" in cookie
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "analyst@example.org"


def test_invalid_credentials_are_generic(client: TestClient, actors: dict[str, Actor]) -> None:
    wrong = login(client, "analyst@example.org", "Wrong-password-123")
    unknown = login(client, "nobody@example.org", "Wrong-password-123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"] == "Invalid email or password."


def test_lockout_after_repeated_failures(
    client: TestClient, actors: dict[str, Actor], settings: Settings, database: Database
) -> None:
    for _ in range(settings.login_max_failed_attempts):
        assert login(client, "viewer@example.org", "Wrong-password-123").status_code == 401
    # Correct password is now refused while locked (same generic message).
    assert login(client, "viewer@example.org").status_code == 401
    with database.session() as session:
        user = session.query(User).filter_by(email="viewer@example.org").one()
        assert user.locked_until is not None
        actions = [a.action for a in session.query(AuditLog).filter_by(actor_user_id=user.id)]
    assert "auth.login.locked" in actions and actions.count("auth.login.failure") == settings.login_max_failed_attempts


def test_refresh_rotates_and_logout_revokes(client: TestClient, actors: dict[str, Actor]) -> None:
    access = login(client, "analyst@example.org").json()["access_token"]
    refreshed = client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert refreshed.status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}).status_code == 204
    # Both the old access token and the refresh cookie are now revoked (token_version bumped).
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_rejects_foreign_origin(client: TestClient, actors: dict[str, Actor]) -> None:
    login(client, "analyst@example.org")
    response = client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "origin_not_allowed"


def test_change_password_revokes_existing_tokens(client: TestClient, actors: dict[str, Actor]) -> None:
    analyst = actors["analyst"]
    weak = client.post(
        "/api/v1/auth/change-password", headers=analyst.headers, json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    bad = client.post(
        "/api/v1/auth/change-password",
        headers=analyst.headers,
        json={"current_password": "Wrong-password-1", "new_password": "Another-Strong-Pass-42"},
    )
    assert bad.status_code == 401
    ok = client.post(
        "/api/v1/auth/change-password",
        headers=analyst.headers,
        json={"current_password": PASSWORD, "new_password": "Another-Strong-Pass-42"},
    )
    assert ok.status_code == 204
    assert client.get("/api/v1/auth/me", headers=analyst.headers).status_code == 401
    assert login(client, "analyst@example.org", "Another-Strong-Pass-42").status_code == 200


def test_login_rate_limit(app, client: TestClient, actors: dict[str, Actor]) -> None:  # type: ignore[no-untyped-def]
    app.state.settings = app.state.settings.model_copy(update={"rate_limit_enabled": True, "rate_limit_login": "3/minute"})
    codes = [login(client, "nobody@example.org", "Wrong-password-1").status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    limited = login(client, "nobody@example.org", "Wrong-password-1")
    assert int(limited.headers["retry-after"]) >= 1 and limited.json()["error"]["code"] == "rate_limited"


def test_deactivated_user_token_rejected(client: TestClient, actors: dict[str, Actor]) -> None:
    response = client.patch(
        f"/api/v1/admin/users/{actors['analyst2'].user.id}", headers=actors["admin"].headers, json={"is_active": False}
    )
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=actors["analyst2"].headers).status_code == 401
    assert login(client, "analyst2@example.org").status_code == 401
