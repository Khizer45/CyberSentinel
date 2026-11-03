"""FR-03/04/05/19, SEC-04, SEC-11: uploads are constrained, validated, owner-scoped and safely deleted."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import Database
from app.models import Dataset
from tests.conftest import Actor, upload
from tests.fixtures.data import cic_traffic_labelling_csv, unsw_csv


def test_valid_upload_is_validated_and_reported(client: TestClient, actors: dict[str, Actor]) -> None:
    response = upload(client, actors["analyst"], unsw_csv(rows=150), name="Test flows")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "validated" and body["row_count"] == 150 and body["schema_version"] == "unsw-nb15-flow-v1"
    assert body["has_ground_truth"] is True and body["owner"]["email"] == "analyst@example.org"
    report = body["validation_report"]
    assert report["accepted"] and report["schema_detection"]["mode"] == "auto"
    assert "storage_key" not in body and "path" not in str(body).lower().replace("schema", "")


def test_raw_cic_traffic_labelling_upload(client: TestClient, actors: dict[str, Actor]) -> None:
    response = upload(client, actors["analyst"], cic_traffic_labelling_csv(rows=60), filename="Friday.pcap_ISCX.csv")
    assert response.status_code == 201, response.text
    report = response.json()["validation_report"]
    assert report["encoding"] == "cp1252" and report["columns"]["known_duplicate_columns"] == ["fwd_header_length"]
    assert report["data_quality"]["non_finite_values"]["flow_bytes_s"] == 3


def test_rejections_keep_report_but_delete_file(
    client: TestClient, actors: dict[str, Actor], database: Database, settings: Settings
) -> None:
    content = unsw_csv(rows=20).replace(b"rate,", b"rate_renamed,", 1)
    response = upload(client, actors["analyst"], content)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "dataset_rejected" and "rate" in error["details"]["missing_features"]
    with database.session() as session:
        rejected = session.get(Dataset, uuid.UUID(error["details"]["dataset_id"]))
        assert rejected.status == "rejected" and rejected.storage_key is None
    assert not any(p.is_file() for p in settings.upload_dir.rglob("*"))


def test_upload_abuse_cases(client: TestClient, actors: dict[str, Actor], settings: Settings) -> None:
    analyst = actors["analyst"]
    assert upload(client, analyst, unsw_csv(rows=5), filename="flows.exe").status_code == 415
    assert upload(client, analyst, unsw_csv(rows=5), content_type="application/x-msdownload").status_code == 415
    assert upload(client, analyst, b"\x89PNG\r\n\x1a\n\x00\x00binary", filename="image.csv").status_code == 422
    assert upload(client, analyst, b"", filename="empty.csv").status_code == 422
    header_only = unsw_csv(rows=1).split(b"\n")[0] + b"\n"
    assert upload(client, analyst, header_only).json()["error"]["code"] == "dataset_rejected"
    duplicated = unsw_csv(rows=5).replace(b"sbytes", b"spkts", 1)
    assert upload(client, analyst, duplicated).status_code == 422
    oversized = b"x" * (settings.max_upload_bytes + 1024)
    assert upload(client, analyst, oversized).status_code == 413
    malformed = unsw_csv(rows=10).replace(b"\n", b",extra\n", 3)
    assert upload(client, analyst, malformed).status_code == 422
    traversal = upload(client, analyst, unsw_csv(rows=5, seed=3), filename="../../etc/passwd.csv")
    assert traversal.status_code == 201 and traversal.json()["original_filename"] == "passwd.csv"


def test_formula_like_and_script_names_are_stored_as_text(client: TestClient, actors: dict[str, Actor]) -> None:
    response = upload(client, actors["analyst"], unsw_csv(rows=5, seed=9), name="<script>alert(1)</script>")
    assert response.status_code == 201 and response.json()["name"] == "<script>alert(1)</script>"


def test_duplicate_upload_conflicts(client: TestClient, actors: dict[str, Actor]) -> None:
    content = unsw_csv(rows=30, seed=4)
    first = upload(client, actors["analyst"], content)
    second = upload(client, actors["analyst"], content)
    assert second.status_code == 409 and second.json()["error"]["details"]["dataset_id"] == first.json()["id"]
    # Another analyst may upload the same file (ownership is per user).
    assert upload(client, actors["analyst2"], content).status_code == 201


def test_ownership_isolation_and_pagination(client: TestClient, actors: dict[str, Actor]) -> None:
    mine = [upload(client, actors["analyst"], unsw_csv(rows=10, seed=s)).json()["id"] for s in range(3)]
    other = upload(client, actors["analyst2"], unsw_csv(rows=10, seed=99)).json()["id"]
    listing = client.get("/api/v1/datasets", headers=actors["analyst"].headers, params={"limit": 2}).json()
    assert listing["total"] == 3 and len(listing["items"]) == 2 and listing["limit"] == 2
    assert client.get(f"/api/v1/datasets/{other}", headers=actors["analyst"].headers).status_code == 404
    assert client.delete(f"/api/v1/datasets/{other}", headers=actors["analyst"].headers).status_code == 404
    admin_view = client.get("/api/v1/datasets", headers=actors["admin"].headers).json()
    assert admin_view["total"] == 4 and set(mine) <= {d["id"] for d in admin_view["items"]}
    bad_sort = client.get("/api/v1/datasets", headers=actors["analyst"].headers, params={"sort": "name; DROP TABLE users"})
    assert bad_sort.status_code == 400
    injection = client.get("/api/v1/datasets", headers=actors["analyst"].headers, params={"q": "' OR '1'='1"})
    assert injection.status_code == 200 and injection.json()["total"] == 0


def test_soft_delete_removes_file_and_keeps_metadata(client: TestClient, actors: dict[str, Actor], settings: Settings) -> None:
    dataset_id = upload(client, actors["analyst"], unsw_csv(rows=10)).json()["id"]
    assert any(p.is_file() for p in settings.upload_dir.rglob("*.csv"))
    assert client.delete(f"/api/v1/datasets/{dataset_id}", headers=actors["analyst"].headers).status_code == 204
    assert not any(p.is_file() for p in settings.upload_dir.rglob("*.csv"))
    deleted = client.get(f"/api/v1/datasets/{dataset_id}", headers=actors["analyst"].headers).json()
    assert deleted["status"] == "deleted" and deleted["deleted_at"] is not None
    assert client.delete(f"/api/v1/datasets/{dataset_id}", headers=actors["analyst"].headers).status_code == 404
