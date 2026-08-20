from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import create_app
from app.errors import DatabaseUnavailableError, ResultNotReadyError
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "analytics_snapshot_success.json"
)


class RecordingSnapshotRepository:
    def __init__(self, missing: set[tuple[str, str]] | None = None) -> None:
        self.delegate = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)
        self.calls: list[tuple[str, str]] = []
        self.missing = missing or set()

    def fetch(self, module_key: str, entity_key: str) -> dict:
        self.calls.append((module_key, entity_key))
        if (module_key, entity_key) in self.missing:
            raise ResultNotReadyError()
        return self.delegate.fetch(module_key, entity_key)


def fixture_app(analytics_repository=None):
    return create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "fixture",
            "ANALYTICS_DATA_SOURCE": "fixture",
            "HIGH_COST_MODEL_PATH": None,
        },
        analytics_repository=analytics_repository,
    )


def test_disease_index_reads_the_frozen_index_entity_without_recomputation():
    repository = RecordingSnapshotRepository()
    response = fixture_app(repository).test_client().get("/api/v1/diseases")

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == "OK"
    assert body["message"] == "success"
    assert body["data"]["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert body["data"]["generated_at"] == "2026-08-18T08:00:00.000000Z"
    assert body["data"]["sections"][0]["key"] == "top10"
    assert response.headers["X-Trace-ID"] == body["trace_id"]
    assert repository.calls == [("diseases", "index")]


def test_disease_profile_reads_the_profile_entity_and_preserves_section_order():
    repository = RecordingSnapshotRepository()
    response = fixture_app(repository).test_client().get("/api/v1/diseases/NVS005")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["title"] == "HEART FAILURE"
    assert [section["key"] for section in data["sections"]] == [
        "age",
        "gender",
        "severity",
        "mortality",
        "procedures",
        "hospitals",
    ]
    assert {metric["key"] for metric in data["metrics"]} >= {
        "record_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
    }
    assert repository.calls == [
        ("diseases", "index"),
        ("diseases", "profile:NVS005"),
    ]


def test_index_and_profile_share_snapshot_metadata():
    client = fixture_app().test_client()
    index = client.get("/api/v1/diseases").get_json()["data"]
    profile = client.get("/api/v1/diseases/INF012").get_json()["data"]

    assert (index["data_version"], index["generated_at"]) == (
        profile["data_version"],
        profile["generated_at"],
    )


def test_legal_enum_without_published_profile_returns_empty_success():
    repository = RecordingSnapshotRepository({("diseases", "profile:NVS005")})
    response = fixture_app(repository).test_client().get("/api/v1/diseases/NVS005")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == {"diagnosis_code": "NVS005"}
    assert data["metrics"] == []
    assert data["sections"] == []
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"


def test_missing_index_is_a_real_not_ready_dependency_failure():
    repository = RecordingSnapshotRepository({("diseases", "index")})
    response = fixture_app(repository).test_client().get("/api/v1/diseases")

    assert response.status_code == 503
    assert response.get_json()["code"] == "RESULT_NOT_READY"
    assert response.get_json()["data"] is None


def test_database_failure_is_not_converted_to_empty_result():
    class FailingRepository:
        def fetch(self, module_key: str, entity_key: str) -> dict:
            raise DatabaseUnavailableError()

    response = fixture_app(FailingRepository()).test_client().get("/api/v1/diseases")

    assert response.status_code == 503
    assert response.get_json()["code"] == "DATABASE_UNAVAILABLE"


def test_invalid_snapshot_is_rejected_before_response():
    class InvalidRepository:
        def fetch(self, module_key: str, entity_key: str) -> dict:
            return {
                "payload": {
                    "title": "bad",
                    "description": "bad",
                    "metrics": [],
                    "sections": [
                        {"key": "ranking", "title": "bad", "type": "line", "items": []}
                    ],
                },
                "data_version": "fixture:bad:v1",
                "generated_at": "2026-08-18T08:00:00.000000Z",
            }

    response = fixture_app(InvalidRepository()).test_client().get("/api/v1/diseases")

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"


def test_corrupt_fixture_is_a_configuration_error(tmp_path):
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{not-json", encoding="utf-8")
    repository = FixtureAnalyticsSnapshotRepository(corrupt_path)

    response = fixture_app(repository).test_client().get("/api/v1/diseases")

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVER_MISCONFIGURED"


@pytest.mark.parametrize("path", ["/api/v1/diseases", "/api/v1/diseases/NVS005"])
def test_unknown_query_parameters_are_rejected(path):
    response = fixture_app().test_client().get(f"{path}?sql=select")

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INVALID_QUERY_PARAMETER"
    assert body["details"] == {"parameters": ["sql"]}
    assert body["data"] is None


def test_unknown_diagnosis_code_is_rejected_without_profile_lookup():
    repository = RecordingSnapshotRepository()
    response = fixture_app(repository).test_client().get("/api/v1/diseases/UNKNOWN")

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INVALID_QUERY_PARAMETER"
    assert body["details"] == {"parameter": "diagnoses"}
    assert repository.calls == [("diseases", "index")]


@pytest.mark.parametrize("path", ["/api/v1/diseases", "/api/v1/diseases/NVS005"])
def test_get_request_body_is_rejected(path):
    response = fixture_app().test_client().get(
        path,
        data=json.dumps({"diagnosis_code": "NVS005"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FORMAT"


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "POST", "PUT", "DELETE"])
@pytest.mark.parametrize("path", ["/api/v1/diseases", "/api/v1/diseases/NVS005"])
def test_disease_endpoints_are_get_only(method, path):
    response = fixture_app().test_client().open(path, method=method)

    assert response.status_code == 405
    if method != "HEAD":
        assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"
