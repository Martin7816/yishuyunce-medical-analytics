from __future__ import annotations

from pathlib import Path

from app import create_app


def fixture_app(**kwargs):
    return create_app(
        {"TESTING": True, "TOP10_DATA_SOURCE": "fixture", "ANALYTICS_DATA_SOURCE": "fixture"},
        **kwargs,
    )


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
        versions.add(body["data"]["data_version"])
    assert versions == {"fixture:sparcs_full_analytics:v1"}


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
