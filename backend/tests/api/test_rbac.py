"""FR-02 / SEC-02: role matrix enforced server-side for every protected route, plus ownership isolation."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import Actor

ANY = uuid.uuid4()
# (method, path, roles allowed) — "allowed" means the request passes authorization (it may still 404/400 later).
MATRIX = [
    ("GET", "/api/v1/auth/me", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/metrics/summary", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/metrics/trends", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/metrics/models", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/models", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/experiments", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/dataset-schemas", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/risk-policy", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/system/info", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/reports/summary", {"admin", "analyst", "viewer"}),
    ("GET", "/api/v1/datasets", {"admin", "analyst"}),
    ("GET", f"/api/v1/datasets/{ANY}", {"admin", "analyst"}),
    ("DELETE", f"/api/v1/datasets/{ANY}", {"admin", "analyst"}),
    ("GET", "/api/v1/analyses", {"admin", "analyst"}),
    ("GET", f"/api/v1/analyses/{ANY}", {"admin", "analyst"}),
    ("POST", f"/api/v1/analyses/{ANY}/cancel", {"admin", "analyst"}),
    ("GET", f"/api/v1/analyses/{ANY}/predictions", {"admin", "analyst"}),
    ("GET", f"/api/v1/predictions/{ANY}", {"admin", "analyst"}),
    ("GET", "/api/v1/alerts", {"admin", "analyst"}),
    ("GET", f"/api/v1/alerts/{ANY}", {"admin", "analyst"}),
    ("GET", "/api/v1/admin/users", {"admin"}),
    ("GET", f"/api/v1/admin/users/{ANY}", {"admin"}),
    ("GET", "/api/v1/audit-logs", {"admin"}),
    ("POST", f"/api/v1/models/{ANY}/verify", {"admin"}),
]


@pytest.mark.parametrize(("method", "path", "allowed"), MATRIX)
def test_role_matrix(client: TestClient, actors: dict[str, Actor], method: str, path: str, allowed: set[str]) -> None:
    assert client.request(method, path).status_code == 401
    for role in ("admin", "analyst", "viewer"):
        status = client.request(method, path, headers=actors[role].headers).status_code
        if role in allowed:
            assert status not in (401, 403), (role, method, path, status)
        else:
            assert status == 403, (role, method, path, status)


def test_privilege_escalation_blocked(client: TestClient, actors: dict[str, Actor]) -> None:
    analyst = actors["analyst"]
    assert (
        client.patch(f"/api/v1/admin/users/{analyst.user.id}", headers=analyst.headers, json={"role": "admin"}).status_code == 403
    )
    assert (
        client.post(
            "/api/v1/admin/users",
            headers=analyst.headers,
            json={"email": "x@example.org", "display_name": "x", "role": "admin", "password": "Strong-Pass-12345"},
        ).status_code
        == 403
    )
    # Mass assignment: unknown fields such as role in a profile update are rejected.
    response = client.patch("/api/v1/auth/me", headers=analyst.headers, json={"display_name": "A", "role": "admin"})
    assert response.status_code == 400


def test_denied_access_is_audited(client: TestClient, actors: dict[str, Actor]) -> None:
    client.get("/api/v1/audit-logs", headers=actors["viewer"].headers)
    logs = client.get("/api/v1/audit-logs", headers=actors["admin"].headers, params={"action": "access.denied"}).json()
    assert logs["total"] >= 1 and logs["items"][0]["outcome"] == "denied"
