"""FR-17 / FR-18 / SEC-09: user administration safeguards and secret-free audit trail."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, Actor

NEW_USER = {
    "email": "New.Analyst@Example.org",
    "display_name": "New Analyst",
    "role": "analyst",
    "password": "Strong-Passphrase-2026",
}


def test_admin_creates_and_manages_users(client: TestClient, actors: dict[str, Actor]) -> None:
    admin = actors["admin"].headers
    created = client.post("/api/v1/admin/users", headers=admin, json=NEW_USER)
    assert created.status_code == 201 and created.json()["email"] == "new.analyst@example.org"
    assert client.post("/api/v1/admin/users", headers=admin, json=NEW_USER).status_code == 409
    weak = client.post("/api/v1/admin/users", headers=admin, json={**NEW_USER, "email": "w@example.org", "password": "weak"})
    assert weak.status_code == 422
    user_id = created.json()["id"]
    assert client.patch(f"/api/v1/admin/users/{user_id}", headers=admin, json={"role": "viewer"}).json()["role"] == "viewer"
    listing = client.get("/api/v1/admin/users", headers=admin, params={"q": "new.analyst", "role": "viewer"}).json()
    assert listing["total"] == 1
    reset = client.post(
        f"/api/v1/admin/users/{user_id}/reset-password", headers=admin, json={"new_password": "Reset-Passphrase-2026"}
    )
    assert reset.status_code == 204
    login = client.post("/api/v1/auth/login", json={"email": "new.analyst@example.org", "password": "Reset-Passphrase-2026"})
    assert login.status_code == 200 and login.json()["user"]["role"] == "viewer"


def test_last_admin_cannot_be_removed(client: TestClient, actors: dict[str, Actor]) -> None:
    admin = actors["admin"]
    for change in ({"is_active": False}, {"role": "analyst"}):
        response = client.patch(f"/api/v1/admin/users/{admin.user.id}", headers=admin.headers, json=change)
        assert response.status_code == 409 and response.json()["error"]["code"] == "last_admin"


def test_role_change_revokes_tokens(client: TestClient, actors: dict[str, Actor]) -> None:
    target = actors["analyst"]
    client.patch(f"/api/v1/admin/users/{target.user.id}", headers=actors["admin"].headers, json={"role": "viewer"})
    assert client.get("/api/v1/auth/me", headers=target.headers).status_code == 401


def test_audit_trail_contains_events_without_secrets(client: TestClient, actors: dict[str, Actor]) -> None:
    client.post("/api/v1/auth/login", json={"email": "analyst@example.org", "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": "analyst@example.org", "password": "Wrong-password-99"})
    client.post("/api/v1/admin/users", headers=actors["admin"].headers, json=NEW_USER)
    logs = client.get("/api/v1/audit-logs", headers=actors["admin"].headers, params={"limit": 100}).json()
    actions = {item["action"] for item in logs["items"]}
    assert {"auth.login.success", "auth.login.failure", "user.create"} <= actions
    dump = str(logs).lower()
    assert PASSWORD.lower() not in dump and "wrong-password" not in dump and "argon2" not in dump
    assert all(item["request_id"] for item in logs["items"] if item["action"].startswith("auth."))
    failures = client.get("/api/v1/audit-logs", headers=actors["admin"].headers, params={"outcome": "failure"}).json()
    assert all(item["outcome"] == "failure" for item in failures["items"])
