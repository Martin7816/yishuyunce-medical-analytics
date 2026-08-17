from __future__ import annotations

import json
from pathlib import Path

from app import create_app
from app.errors import (
    DatabaseUnavailableError,
    ResultNotReadyError,
    ServerMisconfiguredError,
)


SUCCESS_SNAPSHOT = {
    "metric": "disease_case_count_top10",
    "unit": "discharge_records",
    "data_version": "fixture:sparcs_mvp_sample:v1",
    "generated_at": "2026-08-17T00:00:00.000000Z",
    "items": [
        {"rank": 1, "diagnosis_name": "ALPHA", "case_count": 3},
        {"rank": 2, "diagnosis_name": "BETA", "case_count": 2},
    ],
}


class StaticRepository:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def fetch(self):
        return self.snapshot


class RaisingRepository:
    def __init__(self, error):
        self.error = error

    def fetch(self):
        raise self.error


def test_success_response_has_stable_contract(make_client):
    client = make_client(StaticRepository(SUCCESS_SNAPSHOT))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"code", "message", "data", "trace_id"}
    assert body["code"] == "OK"
    assert body["data"]["metric"] == "disease_case_count_top10"
    assert body["data"]["unit"] == "discharge_records"
    assert body["data"]["data_version"] == "fixture:sparcs_mvp_sample:v1"
    assert body["data"]["generated_at"] == "2026-08-17T00:00:00.000000Z"
    assert body["data"]["items"] == SUCCESS_SNAPSHOT["items"]
    assert response.headers["X-Trace-ID"] == body["trace_id"]


def test_fixed_success_fixture_matches_frontend_mock():
    app = create_app(
        {"TESTING": True, "TOP10_DATA_SOURCE": "fixture", "TOP10_FIXTURE_STATE": "success"}
    )
    response = app.test_client().get("/api/v1/diseases/top10")
    actual = response.get_json()

    mock_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "mocks"
        / "disease-top10-success.json"
    )
    expected = json.loads(mock_path.read_text(encoding="utf-8"))
    actual["trace_id"] = expected["trace_id"]

    assert response.status_code == 200
    assert len(actual["data"]["items"]) == 10
    assert actual == expected


def test_legal_empty_snapshot_returns_empty_items(make_client):
    snapshot = {**SUCCESS_SNAPSHOT, "items": []}
    client = make_client(StaticRepository(snapshot))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 200
    assert response.get_json()["data"]["items"] == []


def test_query_parameter_is_rejected(make_client):
    client = make_client(StaticRepository(SUCCESS_SNAPSHOT))
    response = client.get("/api/v1/diseases/top10?limit=5")

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INVALID_QUERY_PARAMETER"
    assert body["details"] == {"parameters": ["limit"]}
    assert body["data"] is None


def test_get_body_is_rejected(make_client):
    client = make_client(StaticRepository(SUCCESS_SNAPSHOT))
    response = client.get(
        "/api/v1/diseases/top10",
        data='{"limit": 5}',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FORMAT"


def test_wrong_method_uses_json_error(make_client):
    client = make_client(StaticRepository(SUCCESS_SNAPSHOT))
    response = client.post("/api/v1/diseases/top10")

    assert response.status_code == 405
    assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_database_failure_is_dependency_error(make_client):
    client = make_client(RaisingRepository(DatabaseUnavailableError()))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 503
    assert response.get_json()["code"] == "DATABASE_UNAVAILABLE"


def test_unpublished_result_is_not_misreported_as_empty(make_client):
    client = make_client(RaisingRepository(ResultNotReadyError()))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 503
    assert response.get_json()["code"] == "RESULT_NOT_READY"


def test_missing_configuration_has_stable_error(make_client):
    client = make_client(RaisingRepository(ServerMisconfiguredError()))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVER_MISCONFIGURED"


def test_mysql_mode_detects_missing_required_configuration():
    app = create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "mysql",
            "MYSQL_HOST": None,
            "MYSQL_USER": None,
            "MYSQL_DATABASE": None,
        }
    )
    response = app.test_client().get("/api/v1/diseases/top10")

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVER_MISCONFIGURED"


def test_unexpected_exception_does_not_leak_details(make_client):
    client = make_client(RaisingRepository(RuntimeError("secret detail")))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 500
    body = response.get_json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "secret detail" not in body["message"]


def test_invalid_published_result_is_rejected(make_client):
    snapshot = {
        **SUCCESS_SNAPSHOT,
        "items": [{"rank": 2, "diagnosis_name": "ALPHA", "case_count": 3}],
    }
    client = make_client(StaticRepository(snapshot))
    response = client.get("/api/v1/diseases/top10")

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"
