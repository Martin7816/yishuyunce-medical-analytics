from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import create_app
from app.errors import (
    DatabaseUnavailableError,
    ResultNotReadyError,
)
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "analytics_snapshot_success.json"
)
FIXTURE_VERSION = "fixture:sparcs_full_analytics:v1"
FIXTURE_GENERATED_AT = "2026-08-18T08:00:00.000000Z"


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


class RecordingSnapshotRepository:
    def __init__(self, result=None, error=None):
        self.delegate = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def fetch(self, module_key: str, entity_key: str) -> dict:
        self.calls.append((module_key, entity_key))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return self.delegate.fetch(module_key, entity_key)


def test_summary_uses_the_frozen_service_entity_and_preserves_order():
    repository = RecordingSnapshotRepository()
    response = fixture_app(repository).test_client().get(
        "/api/v1/data-quality/summary"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"code", "message", "data", "trace_id"}
    assert body["code"] == "OK"
    assert response.headers["X-Trace-ID"] == body["trace_id"]

    data = body["data"]
    assert data["data_version"] == FIXTURE_VERSION
    assert data["generated_at"] == FIXTURE_GENERATED_AT
    assert [metric["key"] for metric in data["metrics"]] == [
        "raw_rows",
        "valid_diagnosis_rows",
        "parse_errors",
        "diagnosis_missing",
    ]
    assert [section["key"] for section in data["sections"]] == [
        "storage",
        "fields",
    ]
    assert {
        item["name"]: item["value"]
        for item in data["sections"][0]["items"]
    } == {
        "HDFS": "CHECK_REQUIRED",
        "Hive": "CHECK_REQUIRED",
        "MySQL": "CHECK_REQUIRED",
        "PySpark任务": "FIXTURE_ONLY",
    }
    assert repository.calls == [("data_quality", "summary")]


def test_current_data_version_is_optional_or_explicitly_accepted():
    client = fixture_app().test_client()

    for path in (
        "/api/v1/data-quality/summary",
        f"/api/v1/data-quality/summary?data_version={FIXTURE_VERSION}",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.get_json()["data"]["data_version"] == FIXTURE_VERSION


def test_data_version_and_query_whitelist_errors_expose_only_safe_names():
    client = fixture_app().test_client()

    unknown = client.get("/api/v1/data-quality/summary?unexpected=select")
    assert unknown.status_code == 400
    assert unknown.get_json()["details"] == {"parameters": ["unexpected"]}
    assert "select" not in unknown.get_data(as_text=True)

    invalid_version = client.get(
        "/api/v1/data-quality/summary?data_version=not-published"
    )
    assert invalid_version.status_code == 400
    assert invalid_version.get_json()["details"] == {"parameter": "data_version"}
    assert "not-published" not in invalid_version.get_data(as_text=True)

    repeated = client.get(
        f"/api/v1/data-quality/summary?data_version={FIXTURE_VERSION}"
        f"&data_version={FIXTURE_VERSION}"
    )
    assert repeated.status_code == 400
    assert repeated.get_json()["details"] == {"parameters": ["data_version"]}


def test_data_quality_endpoint_is_get_only_and_body_free():
    client = fixture_app().test_client()

    body = client.get("/api/v1/data-quality/summary", data="{}")
    assert body.status_code == 400
    assert body.get_json()["code"] == "INVALID_REQUEST_FORMAT"

    for method in ("head", "options", "post"):
        response = getattr(client, method)("/api/v1/data-quality/summary")
        assert response.status_code == 405
        if method != "head":
            assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_valid_empty_payload_is_a_versioned_success_not_a_fake_error():
    repository = RecordingSnapshotRepository(
        result={
            "payload": {
                "title": "数据质量与任务管理",
                "description": "当前批次没有可展示的质量明细。",
                "metrics": [],
                "sections": [],
            },
            "data_version": FIXTURE_VERSION,
            "generated_at": FIXTURE_GENERATED_AT,
        }
    )

    response = fixture_app(repository).test_client().get(
        "/api/v1/data-quality/summary"
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["metrics"] == []
    assert data["sections"] == []
    assert data["data_version"] == FIXTURE_VERSION
    assert data["generated_at"] == FIXTURE_GENERATED_AT
    assert repository.calls == [("data_quality", "summary")]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ResultNotReadyError(), 503, "RESULT_NOT_READY"),
        (DatabaseUnavailableError(), 503, "DATABASE_UNAVAILABLE"),
    ],
)
def test_dependency_failures_are_not_converted_to_empty_answers(error, status, code):
    repository = RecordingSnapshotRepository(error=error)
    response = fixture_app(repository).test_client().get(
        "/api/v1/data-quality/summary"
    )

    assert response.status_code == status
    body = response.get_json()
    assert body["code"] == code
    assert body["data"] is None


def test_invalid_snapshot_is_a_safe_service_result_error():
    repository = RecordingSnapshotRepository(
        result={
            "payload": {
                "title": "数据质量与任务管理",
                "description": "broken",
                "metrics": [],
                "sections": [
                    {"key": "storage", "title": "存储", "type": "line", "items": []}
                ],
            },
            "data_version": FIXTURE_VERSION,
            "generated_at": FIXTURE_GENERATED_AT,
        }
    )

    response = fixture_app(repository).test_client().get(
        "/api/v1/data-quality/summary"
    )
    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"
    assert "line" not in response.get_data(as_text=True)


def test_mysql_adapter_and_fixture_share_the_same_route_service(monkeypatch):
    import pymysql

    fixture_document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = next(
        record["payload"]
        for record in fixture_document["records"]
        if record["module_key"] == "data_quality"
        and record["entity_key"] == "summary"
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            assert "analysis_snapshot_result" in query
            assert params == ("data_quality", "summary")

        def fetchone(self):
            return {
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "data_version": "real:test:v1",
                "generated_at": "2026-08-18T08:00:00Z",
            }

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: Connection())
    app = create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "fixture",
            "ANALYTICS_DATA_SOURCE": "mysql",
            "MYSQL_HOST": "db",
            "MYSQL_USER": "reader",
            "MYSQL_DATABASE": "analytics",
            "HIGH_COST_MODEL_PATH": None,
        }
    )

    response = app.test_client().get("/api/v1/data-quality/summary")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["data_version"] == "real:test:v1"
    assert data["generated_at"] == "2026-08-18T08:00:00.000000Z"
    assert data["metrics"] == payload["metrics"]
    assert data["sections"] == payload["sections"]
