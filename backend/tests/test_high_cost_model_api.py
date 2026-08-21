import json
from copy import deepcopy
from pathlib import Path

import pytest

from app import create_app
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository
from app.services.high_cost_model import FEATURES, HighCostModelService


FIXTURE_ARTIFACT = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "high_cost_model.json"
)
FIXTURE_SNAPSHOT = FIXTURE_ARTIFACT.parent / "analytics_snapshot_success.json"

VALID_DOCUMENT = {
    "age_group": "50 to 69",
    "gender": "F",
    "race": "White",
    "ethnicity": "Not Span/Hispanic",
    "hospital_service_area": "New York City",
    "facility_id": "1",
    "admission_type": "Emergency",
    "emergency_indicator": "Y",
}


def make_client(artifact_path=None, analytics_repository=None):
    app = create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "fixture",
            "ANALYTICS_DATA_SOURCE": "fixture",
            "HIGH_COST_MODEL_PATH": (
                str(artifact_path) if artifact_path is not None else None
            ),
        },
        analytics_repository=analytics_repository,
    )
    return app.test_client()


class InvalidModelSnapshotRepository:
    def __init__(self):
        self.delegate = FixtureAnalyticsSnapshotRepository(FIXTURE_SNAPSHOT)

    def fetch(self, module_key, entity_key):
        record = deepcopy(self.delegate.fetch(module_key, entity_key))
        if module_key == "high_cost_model" and entity_key == "metrics":
            record["payload"]["options"]["feature_names"] = ["unapproved_feature"]
        return record


def test_metrics_and_prediction_expose_the_frozen_contract():
    client = make_client()

    metrics = client.get("/api/v1/models/high-cost/metrics")
    assert metrics.status_code == 200
    metrics_data = metrics.get_json()["data"]
    assert metrics_data["model_version"] == "fixture:high_cost_logistic_regression:v1"
    assert metrics_data["threshold_amount"] == 82450.3
    assert metrics_data["feature_names"] == list(FEATURES)
    assert {item["key"] for item in metrics_data["metrics"]} >= {
        "train_rows",
        "test_rows",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "auc",
    }
    assert metrics_data["sections"][0]["key"] == "confusion"

    high = client.post(
        "/api/v1/models/high-cost/predict",
        json=VALID_DOCUMENT,
    )
    assert high.status_code == 200
    high_data = high.get_json()["data"]
    assert high_data["prediction"] == "HIGH_COST"
    assert high_data["fixture_only"] is True
    assert high_data["model_version"] == metrics_data["model_version"]
    assert high_data["data_version"] == metrics_data["data_version"]
    assert 0 < high_data["probability"] < 1
    assert high_data["boundary"] == (
        "Operational classification only; not a diagnosis or treatment recommendation."
    )

    low = client.post(
        "/api/v1/models/high-cost/predict",
        json={
            **VALID_DOCUMENT,
            "age_group": "0 to 17",
            "hospital_service_area": "Other",
            "admission_type": "Elective",
            "emergency_indicator": "N",
        },
    )
    assert low.status_code == 200
    assert low.get_json()["data"]["prediction"] == "NOT_HIGH_COST"


def test_metrics_rejects_invalid_model_metadata():
    response = make_client(
        analytics_repository=InvalidModelSnapshotRepository()
    ).get("/api/v1/models/high-cost/metrics")

    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"


def test_prediction_uses_sigmoid_and_normalizes_unknown_categories_to_other():
    client = make_client()
    document = {**VALID_DOCUMENT, "facility_id": "not-published-in-artifact"}

    response = client.post("/api/v1/models/high-cost/predict", json=document)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["features"]["facility_id"] == "OTHER"
    # -1.1 + .35 + .08 + .2 + .45 + .38 = .36 for the fixture weights.
    assert data["probability"] == pytest.approx(1 / (1 + 2.718281828459045 ** -0.36), abs=1e-6)


@pytest.mark.parametrize(
    "field",
    [
        "total_charges",
        "total_costs",
        "length_of_stay",
        "discharge_disposition",
        "operating_room_procedure",
        "apr_drg_code",
        "surgery",
        "post_discharge_fields",
    ],
)
def test_prediction_rejects_each_known_leakage_field(field):
    document = {**VALID_DOCUMENT, field: "forbidden"}

    response = make_client().post(
        "/api/v1/models/high-cost/predict",
        json=document,
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "LEAKAGE_FIELD_FORBIDDEN"
    assert body["details"] == {"fields": [field]}


def test_prediction_rejects_unknown_fields_without_treating_them_as_leakage():
    response = make_client().post(
        "/api/v1/models/high-cost/predict",
        json={**VALID_DOCUMENT, "unrelated_field": "value"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INVALID_REQUEST_FIELD"
    assert body["details"] == {"fields": ["unrelated_field"]}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.pop("gender"),
        lambda document: document.__setitem__("gender", "  "),
        lambda document: document.__setitem__("race", "unlisted-race"),
    ],
)
def test_prediction_rejects_missing_empty_and_invalid_feature_values(mutate):
    document = dict(VALID_DOCUMENT)
    mutate(document)

    response = make_client().post(
        "/api/v1/models/high-cost/predict",
        json=document,
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FIELD"


def test_prediction_rejects_non_json_and_non_object_bodies():
    client = make_client()

    invalid_json = client.post(
        "/api/v1/models/high-cost/predict",
        data="{not-json",
        content_type="application/json",
    )
    assert invalid_json.status_code == 400
    assert invalid_json.get_json()["code"] == "INVALID_REQUEST_FORMAT"

    array_body = client.post(
        "/api/v1/models/high-cost/predict",
        json=[],
    )
    assert array_body.status_code == 400
    assert array_body.get_json()["code"] == "INVALID_REQUEST_FORMAT"


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "PUT", "DELETE"])
def test_prediction_endpoint_is_post_only(method):
    response = make_client().open(
        "/api/v1/models/high-cost/predict",
        method=method,
    )

    assert response.status_code == 405
    if method != "HEAD":
        assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_prediction_reports_unpublished_model_and_corrupt_configuration(tmp_path):
    missing = make_client(tmp_path / "not-published.json").post(
        "/api/v1/models/high-cost/predict",
        json=VALID_DOCUMENT,
    )
    assert missing.status_code == 503
    assert missing.get_json()["code"] == "RESULT_NOT_READY"

    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{not-json", encoding="utf-8")
    corrupt = make_client(corrupt_path).post(
        "/api/v1/models/high-cost/predict",
        json=VALID_DOCUMENT,
    )
    assert corrupt.status_code == 500
    assert corrupt.get_json()["code"] == "SERVER_MISCONFIGURED"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"intercept": 0}), encoding="utf-8")
    invalid = make_client(invalid_path).post(
        "/api/v1/models/high-cost/predict",
        json=VALID_DOCUMENT,
    )
    assert invalid.status_code == 500
    assert invalid.get_json()["code"] == "SERVER_MISCONFIGURED"


def test_successful_artifact_is_cached_after_first_request(tmp_path):
    artifact_path = tmp_path / "model.json"
    artifact_path.write_text(FIXTURE_ARTIFACT.read_text(encoding="utf-8"), encoding="utf-8")
    service = HighCostModelService(artifact_path)

    first = service.predict(VALID_DOCUMENT)
    artifact_path.write_text("{not-json", encoding="utf-8")
    second = service.predict(VALID_DOCUMENT)

    assert second == first
