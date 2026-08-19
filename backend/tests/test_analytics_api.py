from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from app.errors import DatabaseUnavailableError, ResultNotReadyError, ServerMisconfiguredError
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository
from werkzeug.test import EnvironBuilder


def fixture_app(**kwargs):
    return create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "fixture",
            "ANALYTICS_DATA_SOURCE": "fixture",
            "HIGH_COST_MODEL_PATH": None,
        },
        **kwargs,
    )


class RaisingAnalyticsRepository:
    def __init__(self, error):
        self.error = error

    def fetch(self, module_key, entity_key):
        raise self.error


class RecordingAnalyticsRepository:
    def __init__(self):
        self.keys = []
        self.delegate = FixtureAnalyticsSnapshotRepository(
            Path(__file__).resolve().parents[1]
            / "app"
            / "fixtures"
            / "analytics_snapshot_success.json"
        )

    def fetch(self, module_key, entity_key):
        self.keys.append((module_key, entity_key))
        return self.delegate.fetch(module_key, entity_key)


def test_all_read_endpoints_share_envelope_and_version():
    client = fixture_app().test_client()
    urls = [
        "/api/v1/dashboard/overview", "/api/v1/hospitals", "/api/v1/hospitals/1",
        "/api/v1/diseases", "/api/v1/diseases/NVS005", "/api/v1/cohorts/summary",
        "/api/v1/costs/overview", "/api/v1/risks/overview", "/api/v1/payments/overview",
        "/api/v1/data-quality/summary", "/api/v1/models/high-cost/metrics",
    ]
    versions = set()
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        body = response.get_json()
        assert set(body) == {"code", "message", "data", "trace_id"}
        assert response.headers["X-Trace-ID"] == body["trace_id"]
        versions.add(body["data"]["data_version"])
    assert versions == {"fixture:sparcs_full_analytics:v1"}


def test_dashboard_success_uses_the_frozen_read_interface():
    response = fixture_app().test_client().get("/api/v1/dashboard/overview")

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == "OK"
    assert body["message"] == "success"
    assert response.headers["X-Trace-ID"] == body["trace_id"]
    assert body["data"]["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert [item["key"] for item in body["data"]["metrics"]] == [
        "record_count",
        "facility_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
        "surgical_rate",
        "severe_rate",
    ]
    assert [section["key"] for section in body["data"]["sections"]] == [
        "age",
        "payment",
        "disease_top10",
        "hospital_top10",
        "severity",
    ]


def test_dashboard_get_body_is_rejected():
    response = fixture_app().test_client().get(
        "/api/v1/dashboard/overview", json={"module_key": "dashboard"}
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FORMAT"


def test_dashboard_unknown_query_parameter_is_rejected():
    response = fixture_app().test_client().get(
        "/api/v1/dashboard/overview?facility_id=1"
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INVALID_QUERY_PARAMETER"
    assert body["details"] == {"parameters": ["facility_id"]}


def test_chunked_dashboard_get_body_is_rejected():
    client = fixture_app().test_client()
    environ = EnvironBuilder(
        path="/api/v1/dashboard/overview",
        method="GET",
        data=b'{"module_key":"dashboard"}',
        headers={"Transfer-Encoding": "chunked"},
    ).get_environ()
    environ.pop("CONTENT_LENGTH", None)
    environ["wsgi.input_terminated"] = True

    response = client.open(environ)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FORMAT"


def test_analytics_endpoints_reject_implicit_head_and_options():
    client = fixture_app().test_client()

    head = client.head("/api/v1/dashboard/overview")
    options = client.options("/api/v1/dashboard/overview")

    assert head.status_code == 405
    assert options.status_code == 405
    assert options.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_dashboard_reads_stable_entity_key_without_route_query_logic():
    repository = RecordingAnalyticsRepository()
    response = fixture_app(analytics_repository=repository).test_client().get(
        "/api/v1/dashboard/overview"
    )

    assert response.status_code == 200
    assert repository.keys == [("dashboard", "overview")]


def test_filter_entity_key_order_is_frozen_for_downstream_modules():
    repository = RecordingAnalyticsRepository()
    response = fixture_app(analytics_repository=repository).test_client().get(
        "/api/v1/cohorts/summary?gender=F&age_group=50%20to%2069&admission_type=Emergency"
    )

    assert response.status_code == 200
    assert repository.keys == [
        ("cohorts", "age=*|gender=*|admission=*"),
        ("cohorts", "age=50 to 69|gender=F|admission=Emergency"),
    ]
    assert response.get_json()["data"]["metrics"] == []
    assert response.get_json()["data"]["sections"] == []


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ResultNotReadyError(), 503, "RESULT_NOT_READY"),
        (DatabaseUnavailableError(), 503, "DATABASE_UNAVAILABLE"),
        (ServerMisconfiguredError(), 500, "SERVER_MISCONFIGURED"),
    ],
)
def test_dashboard_dependency_errors_keep_stable_public_mapping(error, status, code):
    response = fixture_app(
        analytics_repository=RaisingAnalyticsRepository(error)
    ).test_client().get("/api/v1/dashboard/overview")

    assert response.status_code == status
    body = response.get_json()
    assert body["code"] == code
    assert body["data"] is None
    assert "password" not in response.get_data(as_text=True).lower()
    assert "select" not in response.get_data(as_text=True).lower()


def test_hospital_comparison_is_server_composed():
    response = fixture_app().test_client().get(
        "/api/v1/hospitals?facility_a=1&facility_b=2&metric=avg_charges"
    )
    assert response.status_code == 200
    assert len(response.get_json()["data"]["comparison"]) == 2


def test_unknown_and_non_whitelisted_filters_are_rejected():
    client = fixture_app().test_client()
    assert client.get("/api/v1/cohorts/summary?sql=select").status_code == 400
    response = client.get("/api/v1/cohorts/summary?age_group=impossible")
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_QUERY_PARAMETER"


def test_cost_dimensions_are_mutually_exclusive():
    response = fixture_app().test_client().get(
        "/api/v1/costs/overview?diagnosis_code=NVS005&facility_id=1"
    )
    assert response.status_code == 400


def test_valid_unpublished_filter_is_a_legal_empty_result():
    response = fixture_app().test_client().get(
        "/api/v1/cohorts/summary?age_group=50%20to%2069"
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["metrics"] == []

    risk = fixture_app().test_client().get("/api/v1/risks/overview?age_group=70%20or%20Older")
    assert risk.status_code == 200
    assert risk.get_json()["data"]["metrics"] == []


def test_prediction_rejects_leakage_and_returns_versioned_result():
    client = fixture_app().test_client()
    features = {
        "age_group": "50 to 69", "gender": "F", "race": "White",
        "ethnicity": "Not Span/Hispanic", "hospital_service_area": "New York City",
        "facility_id": "1", "admission_type": "Emergency", "emergency_indicator": "Y",
    }
    response = client.post("/api/v1/models/high-cost/predict", json=features)
    assert response.status_code == 200
    assert response.get_json()["data"]["data_version"] == "fixture:sparcs_full_analytics:v1"
    features["total_charges"] = "100000"
    rejected = client.post("/api/v1/models/high-cost/predict", json=features)
    assert rejected.status_code == 400
    assert rejected.get_json()["code"] == "LEAKAGE_FIELD_FORBIDDEN"


def test_model_metadata_is_flattened_from_allowed_snapshot_options():
    response = fixture_app().test_client().get("/api/v1/models/high-cost/metrics")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["model_version"] == "fixture:high_cost_logistic_regression:v1"
    assert data["threshold_amount"] == 82450.3
    assert data["feature_names"][-1] == "emergency_indicator"


def test_invalid_snapshot_payload_is_not_served():
    class InvalidRepository:
        def fetch(self, module_key, entity_key):
            return {
                "payload": {
                    "title": "bad",
                    "description": "bad",
                    "metrics": [],
                    "sections": [{"key": "x", "title": "x", "type": "line", "items": []}],
                },
                "data_version": "fixture:bad:v1",
                "generated_at": "2026-08-18T08:00:00.000000Z",
            }

    response = fixture_app(analytics_repository=InvalidRepository()).test_client().get(
        "/api/v1/dashboard/overview"
    )
    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"


class FakeAIClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "get_dashboard_overview", "arguments": "{}"}}],
            }
        return {"role": "assistant", "content": "当前批次显示运营汇总指标；这些是住院出院记录的群体统计，不构成个人医疗判断。"}


def test_ai_tool_call_is_traceable_and_versioned():
    response = fixture_app(ai_client=FakeAIClient()).test_client().post(
        "/api/v1/ai/chat", json={"message": "概括运营情况"}
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool_trace"][0]["tool"] == "get_dashboard_overview"
    assert data["data_versions"] == ["fixture:sparcs_full_analytics:v1"]
    assert data["sources"][0]["metrics"]


def test_ai_rejects_extra_fields_and_missing_key_is_real_error():
    client = fixture_app().test_client()
    assert client.post("/api/v1/ai/chat", json={"message": "hello", "sql": "select 1"}).status_code == 400
    response = client.post("/api/v1/ai/chat", json={"message": "hello"})
    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVER_MISCONFIGURED"


def test_analytics_source_must_be_explicit():
    app = create_app({"TESTING": True, "TOP10_DATA_SOURCE": "fixture", "ANALYTICS_DATA_SOURCE": None})
    response = app.test_client().get("/api/v1/dashboard/overview")
    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVER_MISCONFIGURED"
