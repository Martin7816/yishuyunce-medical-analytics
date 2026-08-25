from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app import create_app
from app.errors import DatabaseUnavailableError, ResultNotReadyError
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "analytics_snapshot_success.json"
)


def fixture_app(repository=None):
    config = {
        "TESTING": True,
        "TOP10_DATA_SOURCE": "fixture",
        "ANALYTICS_DATA_SOURCE": "fixture",
        "HIGH_COST_MODEL_PATH": None,
    }
    kwargs = {}
    if repository is not None:
        kwargs["analytics_repository"] = repository
    return create_app(config, **kwargs)


class RecordingRepository:
    def __init__(self):
        self.delegate = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)
        self.calls = []

    def fetch(self, module_key, entity_key):
        self.calls.append((module_key, entity_key))
        return self.delegate.fetch(module_key, entity_key)


class NonDiseaseLabelRepository:
    def __init__(self):
        self.delegate = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)

    def fetch(self, module_key, entity_key):
        result = self.delegate.fetch(module_key, entity_key)
        if (module_key, entity_key) != ("diseases", "index"):
            return result
        payload = deepcopy(result["payload"])
        section = next(section for section in payload["sections"] if section["key"] == "top10")
        section["items"].insert(0, {"name": "LIVEBORN", "value": 1})
        result["payload"] = payload
        return result


def test_disease_index_keeps_published_top10_and_enum_order():
    response = fixture_app().test_client().get("/api/v1/diseases")

    assert response.status_code == 200
    data = response.get_json()["data"]
    top10 = next(section for section in data["sections"] if section["key"] == "top10")
    assert len(top10["items"]) == 10
    assert [item["name"] for item in top10["items"][:3]] == [
        "SEPTICEMIA",
        "CORONAVIRUS DISEASE 2019 (COVID-19)",
        "HEART FAILURE",
    ]
    assert [item["value"] for item in data["options"]["diagnoses"]] == [
        "NVS005",
        "INF012",
    ]


def test_disease_snapshot_rejects_non_disease_label():
    response = fixture_app(NonDiseaseLabelRepository()).test_client().get(
        "/api/v1/diseases"
    )

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"


def test_disease_profile_uses_index_then_profile_entity_and_required_sections():
    repository = RecordingRepository()
    response = fixture_app(repository).test_client().get(
        "/api/v1/diseases/NVS005"
    )

    assert response.status_code == 200
    assert repository.calls == [
        ("diseases", "index"),
        ("diseases", "profile:NVS005"),
    ]
    data = response.get_json()["data"]
    assert {metric["key"] for metric in data["metrics"]} >= {
        "record_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
        "surgical_rate",
        "severe_rate",
    }
    assert [section["key"] for section in data["sections"]] == [
        "age",
        "gender",
        "severity",
        "mortality",
        "procedures",
        "hospitals",
    ]


def test_disease_profile_keeps_batch_metadata_consistent_with_index():
    client = fixture_app().test_client()
    index = client.get("/api/v1/diseases").get_json()["data"]
    profile = client.get("/api/v1/diseases/NVS005").get_json()["data"]

    assert profile["data_version"] == index["data_version"]
    assert profile["generated_at"] == index["generated_at"]


def test_legal_unpublished_disease_profile_is_empty_but_versioned():
    base = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)

    class MissingProfileRepository:
        def fetch(self, module_key, entity_key):
            if (module_key, entity_key) == ("diseases", "profile:INF012"):
                raise ResultNotReadyError()
            return base.fetch(module_key, entity_key)

    response = fixture_app(MissingProfileRepository()).test_client().get(
        "/api/v1/diseases/INF012"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == {"diagnosis_code": "INF012"}
    assert data["metrics"] == []
    assert data["sections"] == []
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert data["generated_at"]


def test_missing_disease_index_and_database_failure_are_not_empty_answers():
    class RaisingRepository:
        def __init__(self, error):
            self.error = error

        def fetch(self, module_key, entity_key):
            raise self.error

    not_ready = fixture_app(
        RaisingRepository(ResultNotReadyError())
    ).test_client().get("/api/v1/diseases")
    unavailable = fixture_app(
        RaisingRepository(DatabaseUnavailableError())
    ).test_client().get("/api/v1/diseases")

    assert not_ready.status_code == 503
    assert not_ready.get_json()["code"] == "RESULT_NOT_READY"
    assert unavailable.status_code == 503
    assert unavailable.get_json()["code"] == "DATABASE_UNAVAILABLE"


def test_disease_path_and_query_validation_are_safe():
    client = fixture_app().test_client()

    invalid_code = client.get("/api/v1/diseases/UNKNOWN")
    unknown_query = client.get("/api/v1/diseases?diagnosis_code=NVS005")

    assert invalid_code.status_code == 400
    assert invalid_code.get_json()["details"] == {"parameter": "diagnosis_code"}
    assert "UNKNOWN" not in invalid_code.get_data(as_text=True)
    assert unknown_query.status_code == 400
    assert unknown_query.get_json()["details"] == {
        "parameters": ["diagnosis_code"]
    }


def test_disease_read_routes_are_get_only_and_body_free():
    client = fixture_app().test_client()

    body = client.get("/api/v1/diseases/NVS005", data="{}")
    assert body.status_code == 400
    assert body.get_json()["code"] == "INVALID_REQUEST_FORMAT"

    for method in ("head", "options", "post", "put", "delete"):
        response = getattr(client, method)("/api/v1/diseases")
        assert response.status_code == 405, method
        if method not in {"head"}:
            assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"
