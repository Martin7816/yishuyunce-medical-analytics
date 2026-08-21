from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from app import create_app
from app.errors import (
    DatabaseUnavailableError,
    InvalidServiceResultError,
    ResultNotReadyError,
)
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "analytics_snapshot_success.json"
)


def fixture_app(analytics_repository=None, **overrides):
    config = {
        "TESTING": True,
        "TOP10_DATA_SOURCE": "fixture",
        "ANALYTICS_DATA_SOURCE": "fixture",
        "HIGH_COST_MODEL_PATH": None,
    }
    config.update(overrides)
    kwargs = {}
    if analytics_repository is not None:
        kwargs["analytics_repository"] = analytics_repository
    return create_app(config, **kwargs)


class RecordingPaymentRepository:
    def __init__(self):
        self.delegate = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)
        self.calls = []

    def fetch(self, module_key, entity_key):
        self.calls.append((module_key, entity_key))
        return self.delegate.fetch(module_key, entity_key)


def assert_trace_matches_header(response):
    body = response.get_json()
    assert body["trace_id"] == response.headers["X-Trace-ID"]
    UUID(body["trace_id"])
    return body


def test_payment_wildcard_returns_the_published_payload_without_recalculation():
    response = fixture_app().test_client().get("/api/v1/payments/overview")

    assert response.status_code == 200
    body = assert_trace_matches_header(response)
    assert set(body) == {"code", "message", "data", "trace_id"}
    assert body["code"] == "OK"

    data = body["data"]
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert data["generated_at"] == "2026-08-18T08:00:00.000000Z"
    assert data["filters"] == {}
    assert [metric["key"] for metric in data["metrics"]] == [
        "record_count",
        "avg_charges",
        "median_charges",
    ]
    assert [section["key"] for section in data["sections"]] == [
        "payment",
        "charges",
        "age",
        "diseases",
    ]
    assert len(data["options"]["payment_type"]) == 9
    assert len(data["options"]["age_group"]) == 5
    assert len(next(section for section in data["sections"] if section["key"] == "diseases")["items"]) == 10


@pytest.mark.parametrize(
    ("query", "expected_filters", "expected_entity"),
    [
        (
            "payment_type=Medicare",
            {"payment_type": "Medicare"},
            "payment=Medicare|age=*",
        ),
        (
            "age_group=50%20to%2069",
            {"age_group": "50 to 69"},
            "payment=*|age=50 to 69",
        ),
        (
            "payment_type=Medicare&age_group=50%20to%2069",
            {"payment_type": "Medicare", "age_group": "50 to 69"},
            "payment=Medicare|age=50 to 69",
        ),
    ],
)
def test_payment_filters_use_service_seam_and_frozen_entity_order(
    query, expected_filters, expected_entity
):
    repository = RecordingPaymentRepository()
    response = fixture_app(analytics_repository=repository).test_client().get(
        f"/api/v1/payments/overview?{query}"
    )

    assert response.status_code == 200
    body = assert_trace_matches_header(response)
    data = body["data"]
    assert data["filters"] == expected_filters
    assert data["metrics"] == []
    assert data["sections"] == []
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert repository.calls == [
        ("payments", "payment=*|age=*"),
        ("payments", expected_entity),
    ]


@pytest.mark.parametrize(
    ("query", "details"),
    [
        ("sql=select", {"parameters": ["sql"]}),
        ("payment_type=UNKNOWN", {"parameter": "payment_type"}),
        ("age_group=UNKNOWN", {"parameter": "age_group"}),
        (
            "payment_type=Medicare&payment_type=Medicaid",
            {"parameters": ["payment_type"]},
        ),
    ],
)
def test_payment_filters_reject_unknown_invalid_and_repeated_values(query, details):
    response = fixture_app().test_client().get(
        f"/api/v1/payments/overview?{query}"
    )

    assert response.status_code == 400
    body = assert_trace_matches_header(response)
    assert body["code"] == "INVALID_QUERY_PARAMETER"
    assert body["details"] == details
    assert "UNKNOWN" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ResultNotReadyError(), 503, "RESULT_NOT_READY"),
        (DatabaseUnavailableError(), 503, "DATABASE_UNAVAILABLE"),
        (InvalidServiceResultError(), 500, "SERVICE_RESULT_INVALID"),
    ],
)
def test_payment_base_dependency_failures_keep_stable_public_errors(
    error, status, code
):
    class RaisingRepository:
        def fetch(self, module_key, entity_key):
            assert (module_key, entity_key) == (
                "payments",
                "payment=*|age=*",
            )
            raise error

    response = fixture_app(analytics_repository=RaisingRepository()).test_client().get(
        "/api/v1/payments/overview"
    )

    assert response.status_code == status
    body = assert_trace_matches_header(response)
    assert body["code"] == code
    assert body["data"] is None
    assert "payment=*|age=*" not in response.get_data(as_text=True)


def test_payment_corrupt_payload_maps_to_service_result_invalid_without_leakage():
    class CorruptRepository:
        def fetch(self, module_key, entity_key):
            return {
                "payload": "{not-json",
                "data_version": "real:test:v1",
                "generated_at": "2026-08-19T00:00:00.000000Z",
            }

    response = fixture_app(analytics_repository=CorruptRepository()).test_client().get(
        "/api/v1/payments/overview"
    )

    assert response.status_code == 500
    body = assert_trace_matches_header(response)
    assert body["code"] == "SERVICE_RESULT_INVALID"
    assert "not-json" not in response.get_data(as_text=True)


def test_payment_route_has_no_request_body_and_is_strictly_get_only():
    client = fixture_app().test_client()

    body = client.get(
        "/api/v1/payments/overview",
        data="{}",
        content_type="application/json",
    )
    assert body.status_code == 400
    assert body.get_json()["code"] == "INVALID_REQUEST_FORMAT"

    for method in ("head", "options", "post", "put", "delete"):
        response = getattr(client, method)("/api/v1/payments/overview")
        assert response.status_code == 405
        if method != "head":
            assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_payment_missing_mysql_configuration_is_a_safe_500():
    app = fixture_app(
        ANALYTICS_DATA_SOURCE="mysql",
        MYSQL_HOST=None,
        MYSQL_USER=None,
        MYSQL_DATABASE=None,
    )
    response = app.test_client().get("/api/v1/payments/overview")

    assert response.status_code == 500
    body = assert_trace_matches_header(response)
    assert body["code"] == "SERVER_MISCONFIGURED"
    assert body["data"] is None
