from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app import create_app
from app.errors import (
    DatabaseUnavailableError,
    InvalidServiceResultError,
    ResultNotReadyError,
)
from app.repositories.analytics_snapshot import (
    FixtureAnalyticsSnapshotRepository,
    MySQLAnalyticsSnapshotRepository,
)
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


def test_risk_snapshot_exposes_frozen_metrics_and_sections():
    response = fixture_app().test_client().get('/api/v1/risks/overview')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['data_version'] == 'fixture:sparcs_full_analytics:v1'
    assert data['options']['age_group'] == [
        '0 to 17',
        '18 to 29',
        '30 to 49',
        '50 to 69',
        '70 or Older',
    ]
    assert data['options']['diagnosis_code'] == [
        {'value': 'NVS005', 'label': 'HEART FAILURE'},
        {
            'value': 'INF012',
            'label': 'CORONAVIRUS DISEASE 2019 (COVID-19)',
        },
    ]
    assert [metric['key'] for metric in data['metrics']] == [
        'severity_valid_count',
        'high_risk_count',
        'high_risk_rate',
        'avg_los',
        'avg_charges',
        'avg_costs',
    ]
    metrics = {metric['key']: metric['value'] for metric in data['metrics']}
    assert metrics['severity_valid_count'] == 2099038
    assert metrics['high_risk_rate'] == 0.3336
    assert [section['key'] for section in data['sections']] == [
        'severity',
        'mortality',
        'disposition',
        'age',
        'diseases',
    ]
    assert len(data['sections'][-1]['items']) == 10
    assert data['sections'][-1]['title'] == '高风险疾病 TOP10'


def test_data_quality_exposes_business_field_denominator_evidence():
    response = fixture_app().test_client().get('/api/v1/data-quality/summary')

    assert response.status_code == 200
    data = response.get_json()['data']
    metrics = {metric['key']: metric['value'] for metric in data['metrics']}
    assert metrics['valid_rows'] == 2101588
    assert metrics['severity_valid_rows'] == 2099038
    assert metrics['severity_missing_rows'] == 2550
    assert metrics['severity_valid_rows'] + metrics['severity_missing_rows'] == metrics['valid_rows']
    audit = data['options']['audit']
    assert audit['formula_version'] == 'analytics-denominator-v1'
    assert audit['base_population']['count'] == metrics['valid_rows']
    assert audit['base_population']['filters'] == {
        'discharge_year': '2021',
        'length_of_stay': 'parsed',
    }
    assert audit['fields']['severity']['applicable_count'] == metrics['valid_rows']
    assert audit['fields']['severity']['valid_count'] == metrics['severity_valid_rows']
    assert audit['fields']['severity']['missing_count'] == metrics['severity_missing_rows']
    assert audit['ratios']['severe_rate']['numerator'] == 700276
    assert audit['ratios']['severe_rate']['denominator'] == 2099038
    assert audit['ratios']['emergency_rate']['denominator'] == 2101588
    assert audit['ratios']['surgical_rate']['denominator'] == 2101588
    assert 0 <= audit['ratios']['emergency_rate']['numerator'] <= 2101588
    assert 0 <= audit['ratios']['surgical_rate']['numerator'] <= 2101588
    sections = {section['key']: section['items'] for section in data['sections']}
    assert {'field_validity', 'field_missing'} <= set(sections)
    missing = {item['name']: item['value'] for item in sections['field_missing']}
    assert missing['机构编号'] == 10642
    assert missing['主要操作'] == 576021


class RecordingRiskRepository:
    def __init__(self):
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / 'app'
            / 'fixtures'
            / 'analytics_snapshot_success.json'
        )
        self.delegate = FixtureAnalyticsSnapshotRepository(fixture_path)
        self.base_record = self.delegate.fetch('risks', 'age=*|diagnosis=*')
        self.calls = []

    def fetch(self, module_key, entity_key):
        self.calls.append((module_key, entity_key))
        if module_key != 'risks' or entity_key == 'age=*|diagnosis=*':
            return self.delegate.fetch(module_key, entity_key)

        age, diagnosis = (
            segment.split('=', 1)[1]
            for segment in entity_key.split('|')
        )
        filters = {}
        if age != '*':
            filters['age_group'] = age
        if diagnosis != '*':
            filters['diagnosis_code'] = diagnosis
        record = deepcopy(self.base_record)
        record['payload']['filters'] = filters
        return record


@pytest.mark.parametrize(
    ('query', 'expected_filters', 'expected_entity', 'expected_calls'),
    [
        (
            'age_group=50%20to%2069',
            {'age_group': '50 to 69'},
            'age=50 to 69|diagnosis=*',
            [
                ('risks', 'age=*|diagnosis=*'),
                ('risks', 'age=50 to 69|diagnosis=*'),
            ],
        ),
        (
            'diagnosis_code=NVS005',
            {'diagnosis_code': 'NVS005'},
            'age=*|diagnosis=NVS005',
            [
                ('diseases', 'index'),
                ('risks', 'age=*|diagnosis=*'),
                ('risks', 'age=*|diagnosis=NVS005'),
            ],
        ),
        (
            'diagnosis_code=NVS005&age_group=50%20to%2069',
            {'age_group': '50 to 69', 'diagnosis_code': 'NVS005'},
            'age=50 to 69|diagnosis=NVS005',
            [
                ('diseases', 'index'),
                ('risks', 'age=*|diagnosis=*'),
                ('risks', 'age=50 to 69|diagnosis=NVS005'),
            ],
        ),
    ],
)
def test_risk_filters_use_service_seam_and_frozen_entity_order(
    query, expected_filters, expected_entity, expected_calls
):
    repository = RecordingRiskRepository()
    response = fixture_app(analytics_repository=repository).test_client().get(
        f'/api/v1/risks/overview?{query}'
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['filters'] == expected_filters
    assert data['metrics'] == repository.base_record['payload']['metrics']
    assert data['sections'] == repository.base_record['payload']['sections']
    assert data['data_version'] == 'fixture:sparcs_full_analytics:v1'
    assert repository.calls == expected_calls
    assert repository.calls[-1][1] == expected_entity


@pytest.mark.parametrize(
    ('query', 'details'),
    [
        ('sql=select', {'parameters': ['sql']}),
        ('age_group=Unknown', {'parameter': 'age_group'}),
        ('diagnosis_code=UNKNOWN', {'parameter': 'diagnosis_code'}),
        (
            'age_group=50%20to%2069&age_group=70%20or%20Older',
            {'parameters': ['age_group']},
        ),
        (
            'diagnosis_code=NVS005&diagnosis_code=INF012',
            {'parameters': ['diagnosis_code']},
        ),
    ],
)
def test_risk_filters_reject_unknown_invalid_and_repeated_values(query, details):
    response = fixture_app().test_client().get(
        f'/api/v1/risks/overview?{query}'
    )

    assert response.status_code == 400
    assert response.get_json()['code'] == 'INVALID_QUERY_PARAMETER'
    assert response.get_json()['details'] == details
    assert 'UNKNOWN' not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ('error', 'status', 'code'),
    [
        (ResultNotReadyError(), 503, 'RESULT_NOT_READY'),
        (DatabaseUnavailableError(), 503, 'DATABASE_UNAVAILABLE'),
        (InvalidServiceResultError(), 500, 'SERVICE_RESULT_INVALID'),
    ],
)
def test_risk_base_dependency_failures_keep_stable_public_errors(
    error, status, code
):
    class RaisingRepository:
        def fetch(self, module_key, entity_key):
            assert (module_key, entity_key) == (
                'risks',
                'age=*|diagnosis=*',
            )
            raise error

    response = fixture_app(analytics_repository=RaisingRepository()).test_client().get(
        '/api/v1/risks/overview'
    )

    assert response.status_code == status
    assert response.get_json()['code'] == code
    assert 'age=*|diagnosis=*' not in response.get_data(as_text=True)


def test_risk_valid_unpublished_combination_returns_empty_snapshot():
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / 'app'
        / 'fixtures'
        / 'analytics_snapshot_success.json'
    )
    delegate = FixtureAnalyticsSnapshotRepository(fixture_path)

    class MissingRiskCombinationRepository:
        def fetch(self, module_key, entity_key):
            if module_key == 'risks' and entity_key != 'age=*|diagnosis=*':
                raise ResultNotReadyError()
            return delegate.fetch(module_key, entity_key)

    response = fixture_app(
        analytics_repository=MissingRiskCombinationRepository()
    ).test_client().get(
        '/api/v1/risks/overview?diagnosis_code=NVS005&age_group=50%20to%2069'
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['filters'] == {
        'age_group': '50 to 69',
        'diagnosis_code': 'NVS005',
    }
    assert data['metrics'] == []
    assert data['sections'] == []
    assert data['data_version'] == 'fixture:sparcs_full_analytics:v1'


def test_hospital_comparison_is_server_composed():
    response = fixture_app().test_client().get(
        "/api/v1/hospitals?facility_a=1&facility_b=2&metric=avg_charges"
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == {
        "facility_a": "1",
        "facility_b": "2",
        "metric": "avg_charges",
    }
    assert [profile["title"] for profile in data["comparison"]] == [
        "North Shore University Hospital",
        "NewYork-Presbyterian",
    ]
    assert [metric["key"] for metric in data["comparison"][0]["metrics"]] == [
        "case_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
        "severe_rate",
    ]


def test_hospital_filters_keep_service_order_and_payload_values():
    client = fixture_app().test_client()

    index = client.get("/api/v1/hospitals").get_json()["data"]
    assert "filters" not in index
    assert "comparison" not in index

    profile = client.get("/api/v1/hospitals/1").get_json()["data"]
    selected = client.get("/api/v1/hospitals?facility_a=1").get_json()["data"]
    assert selected["comparison"] == [profile]
    assert selected["filters"] == {"facility_a": "1"}

    metric_only = client.get("/api/v1/hospitals?metric=case_count").get_json()["data"]
    assert metric_only["filters"] == {"metric": "case_count"}
    assert "comparison" not in metric_only

    for metric in (
        "case_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
        "severe_rate",
    ):
        response = client.get(f"/api/v1/hospitals?metric={metric}")
        assert response.status_code == 200
        assert response.get_json()["data"]["filters"]["metric"] == metric


def test_hospital_unknown_invalid_duplicate_and_conflicting_filters_are_rejected():
    client = fixture_app().test_client()

    unknown = client.get("/api/v1/hospitals?sql=select")
    assert unknown.status_code == 400
    assert unknown.get_json()["details"] == {"parameters": ["sql"]}

    invalid = client.get("/api/v1/hospitals?facility_a=secret")
    assert invalid.status_code == 400
    assert invalid.get_json()["details"] == {"parameter": "facility_a"}
    assert "secret" not in invalid.get_data(as_text=True)

    duplicate = client.get("/api/v1/hospitals?facility_a=1&facility_a=2")
    assert duplicate.status_code == 400
    assert duplicate.get_json()["details"] == {"parameters": ["facility_a"]}

    same_facility = client.get("/api/v1/hospitals?facility_a=1&facility_b=1")
    assert same_facility.status_code == 400
    assert same_facility.get_json()["details"] == {
        "parameters": ["facility_a", "facility_b"]
    }


def test_hospital_get_only_and_request_body_contract():
    client = fixture_app().test_client()

    body = client.get("/api/v1/hospitals", data='{"facility_a":"1"}')
    assert body.status_code == 400
    assert body.get_json()["code"] == "INVALID_REQUEST_FORMAT"

    for method in ("post", "head", "options"):
        response = getattr(client, method)("/api/v1/hospitals")
        assert response.status_code == 405, method
        if method != "head":
            assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_chunked_hospital_get_body_is_rejected():
    client = fixture_app().test_client()
    environ = EnvironBuilder(
        path="/api/v1/hospitals",
        method="GET",
        data=b'{"facility_a":"1"}',
        headers={"Transfer-Encoding": "chunked"},
    ).get_environ()
    environ.pop("CONTENT_LENGTH", None)
    environ["wsgi.input_terminated"] = True

    response = client.open(environ)
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FORMAT"


def test_valid_unpublished_hospital_profile_is_a_legal_empty_result():
    fixture_path = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "analytics_snapshot_success.json"
    base = FixtureAnalyticsSnapshotRepository(fixture_path)

    class MissingProfileRepository:
        def fetch(self, module_key, entity_key):
            if module_key == "hospitals" and entity_key == "profile:2":
                raise ResultNotReadyError()
            return base.fetch(module_key, entity_key)

    response = fixture_app(analytics_repository=MissingProfileRepository()).test_client().get(
        "/api/v1/hospitals?facility_a=2"
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == {"facility_a": "2"}
    assert data["metrics"] == []
    assert data["sections"] == []
    assert data["comparison"] == []
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"


def test_unpublished_hospital_module_and_database_failure_are_not_empty_answers():
    class RaisingRepository:
        def __init__(self, error):
            self.error = error

        def fetch(self, module_key, entity_key):
            raise self.error

    not_ready = fixture_app(
        analytics_repository=RaisingRepository(ResultNotReadyError())
    ).test_client().get("/api/v1/hospitals")
    assert not_ready.status_code == 503
    assert not_ready.get_json()["code"] == "RESULT_NOT_READY"

    unavailable = fixture_app(
        analytics_repository=RaisingRepository(DatabaseUnavailableError())
    ).test_client().get("/api/v1/hospitals")
    assert unavailable.status_code == 503
    assert unavailable.get_json()["code"] == "DATABASE_UNAVAILABLE"


def test_damaged_snapshot_and_missing_mysql_configuration_are_safe_500s():
    class BrokenPayloadRepository:
        def fetch(self, module_key, entity_key):
            return {
                "payload": "{not-json",
                "data_version": "fixture:broken:v1",
                "generated_at": "2026-08-18T08:00:00.000000Z",
            }

    broken = fixture_app(analytics_repository=BrokenPayloadRepository()).test_client().get(
        "/api/v1/hospitals"
    )
    assert broken.status_code == 500
    assert broken.get_json()["code"] == "SERVICE_RESULT_INVALID"
    assert "not-json" not in broken.get_data(as_text=True)

    misconfigured = create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "fixture",
            "ANALYTICS_DATA_SOURCE": "mysql",
            "MYSQL_HOST": None,
            "MYSQL_USER": None,
            "MYSQL_DATABASE": None,
            "HIGH_COST_MODEL_PATH": None,
        }
    ).test_client().get("/api/v1/hospitals")
    assert misconfigured.status_code == 500
    assert misconfigured.get_json()["code"] == "SERVER_MISCONFIGURED"


def test_mysql_payload_json_damage_is_a_service_result_error(monkeypatch):
    import pymysql

    from app.repositories.analytics_snapshot import MySQLAnalyticsSnapshotRepository

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            assert params == ("hospitals", "index")

        def fetchone(self):
            return {
                "payload_json": "{broken-json",
                "data_version": "real:test:v1",
                "generated_at": "2026-08-18T08:00:00.000000",
            }

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: Connection())
    repository = MySQLAnalyticsSnapshotRepository(
        {
            "MYSQL_HOST": "db",
            "MYSQL_PORT": 3306,
            "MYSQL_USER": "reader",
            "MYSQL_PASSWORD": "not-used",
            "MYSQL_DATABASE": "analytics",
            "MYSQL_CONNECT_TIMEOUT": 3,
        }
    )

    response = fixture_app(analytics_repository=repository).test_client().get(
        "/api/v1/hospitals"
    )
    assert response.status_code == 500
    assert response.get_json()["code"] == "SERVICE_RESULT_INVALID"


def test_mysql_adapter_reads_cost_entity_with_bound_parameters(monkeypatch):
    import pymysql

    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "fixtures"
        / "analytics_snapshot_success.json"
    )
    document = json.loads(fixture_path.read_text(encoding="utf-8"))
    cost = next(
        record
        for record in document["records"]
        if record["module_key"] == "costs"
    )
    entity = "diagnosis=NVS005|facility=*|severity=Major"

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchone(self):
            return {
                "payload_json": json.dumps(cost["payload"]),
                "data_version": document["data_version"],
                "generated_at": document["generated_at"],
            }

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

        def close(self):
            return None

    connection = Connection()
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: connection)
    repository = MySQLAnalyticsSnapshotRepository(
        {
            "MYSQL_HOST": "db",
            "MYSQL_USER": "reader",
            "MYSQL_DATABASE": "analytics",
        }
    )

    record = repository.fetch("costs", entity)

    assert record["payload"] == cost["payload"]
    assert connection.cursor_instance.params == ("costs", entity)
    assert "module_key" in connection.cursor_instance.query
    assert "entity_key" in connection.cursor_instance.query


def test_unknown_and_non_whitelisted_filters_are_rejected():
    client = fixture_app().test_client()
    assert client.get("/api/v1/cohorts/summary?sql=select").status_code == 400
    response = client.get("/api/v1/cohorts/summary?age_group=impossible")
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_QUERY_PARAMETER"


def test_repeated_query_parameters_are_rejected():
    response = fixture_app().test_client().get(
        "/api/v1/cohorts/summary?age_group=30%20to%2049&age_group=50%20to%2069"
    )
    assert response.status_code == 400
    assert response.get_json()["details"] == {"parameters": ["age_group"]}


def test_analytics_get_routes_reject_head_options_and_post():
    client = fixture_app().test_client()
    urls = [
        "/api/v1/dashboard/overview",
        "/api/v1/hospitals",
        "/api/v1/hospitals/1",
        "/api/v1/diseases",
        "/api/v1/diseases/NVS005",
        "/api/v1/cohorts/summary",
        "/api/v1/costs/overview",
        "/api/v1/risks/overview",
        "/api/v1/payments/overview",
        "/api/v1/data-quality/summary",
        "/api/v1/models/high-cost/metrics",
    ]
    for url in urls:
        assert client.head(url).status_code == 405
        for method in ("options", "post"):
            response = getattr(client, method)(url)
            assert response.status_code == 405, (method, url)
            assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_analytics_get_routes_reject_request_bodies():
    response = fixture_app().test_client().get(
        "/api/v1/dashboard/overview",
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REQUEST_FORMAT"


class MissingProfileRepository:
    def __init__(self):
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "fixtures"
            / "analytics_snapshot_success.json"
        )
        self.delegate = FixtureAnalyticsSnapshotRepository(fixture_path)

    def fetch(self, module_key, entity_key):
        if (module_key, entity_key) in {
            ("hospitals", "profile:2"),
            ("diseases", "profile:INF012"),
        }:
            raise ResultNotReadyError()
        return self.delegate.fetch(module_key, entity_key)


def test_valid_unpublished_profiles_return_empty_results():
    client = fixture_app(analytics_repository=MissingProfileRepository()).test_client()
    for path, expected_filter in (
        ("/api/v1/hospitals/2", {"facility_id": "2"}),
        ("/api/v1/diseases/INF012", {"diagnosis_code": "INF012"}),
    ):
        response = client.get(path)
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["metrics"] == []
        assert data["sections"] == []
        assert data["filters"] == expected_filter


def test_cost_dimensions_are_mutually_exclusive():
    response = fixture_app().test_client().get(
        "/api/v1/costs/overview?diagnosis_code=NVS005&facility_id=1"
    )
    assert response.status_code == 400
    assert response.get_json()["details"] == {
        "parameters": ["diagnosis_code", "facility_id"]
    }


class RecordingCostRepository:
    def __init__(self):
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "fixtures"
            / "analytics_snapshot_success.json"
        )
        self.delegate = FixtureAnalyticsSnapshotRepository(fixture_path)
        self.calls = []

    def fetch(self, module_key, entity_key):
        self.calls.append((module_key, entity_key))
        return self.delegate.fetch(module_key, entity_key)


def test_cost_overview_unfiltered_preserves_published_snapshot():
    response = fixture_app().test_client().get("/api/v1/costs/overview")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == {}
    assert [metric["key"] for metric in data["metrics"]] == [
        "avg_charges",
        "median_charges",
        "p90_charges",
        "avg_costs",
        "charge_cost_gap",
        "daily_charges",
    ]
    assert [section["key"] for section in data["sections"]] == [
        "quantiles",
        "severity",
    ]
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"


@pytest.mark.parametrize(
    ("query", "expected_filter", "expected_entity", "expected_calls"),
    [
        (
            "diagnosis_code=NVS005",
            {"diagnosis_code": "NVS005"},
            "diagnosis=NVS005|facility=*|severity=*",
            [
                ("diseases", "index"),
                ("costs", "diagnosis=*|facility=*|severity=*"),
                ("costs", "diagnosis=NVS005|facility=*|severity=*"),
            ],
        ),
        (
            "facility_id=1",
            {"facility_id": "1"},
            "diagnosis=*|facility=1|severity=*",
            [
                ("hospitals", "index"),
                ("costs", "diagnosis=*|facility=*|severity=*"),
                ("costs", "diagnosis=*|facility=1|severity=*"),
            ],
        ),
        (
            "severity=Major",
            {"severity": "Major"},
            "diagnosis=*|facility=*|severity=Major",
            [
                ("costs", "diagnosis=*|facility=*|severity=*"),
                ("costs", "diagnosis=*|facility=*|severity=Major"),
            ],
        ),
        (
            "diagnosis_code=NVS005&severity=Major",
            {"diagnosis_code": "NVS005", "severity": "Major"},
            "diagnosis=NVS005|facility=*|severity=Major",
            [
                ("diseases", "index"),
                ("costs", "diagnosis=*|facility=*|severity=*"),
                ("costs", "diagnosis=NVS005|facility=*|severity=Major"),
            ],
        ),
    ],
)
def test_cost_filters_use_service_seam_and_frozen_entity_order(
    query, expected_filter, expected_entity, expected_calls
):
    repository = RecordingCostRepository()
    response = fixture_app(analytics_repository=repository).test_client().get(
        f"/api/v1/costs/overview?{query}"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == expected_filter
    assert data["metrics"] == []
    assert data["sections"] == []
    assert data["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert repository.calls == expected_calls
    assert repository.calls[-1][1] == expected_entity


@pytest.mark.parametrize(
    ("query", "details"),
    [
        ("sql=select", {"parameters": ["sql"]}),
        ("diagnosis_code=UNKNOWN", {"parameter": "diagnosis_code"}),
        ("facility_id=UNKNOWN", {"parameter": "facility_id"}),
        ("severity=UNKNOWN", {"parameter": "severity"}),
        (
            "diagnosis_code=NVS005&diagnosis_code=INF012",
            {"parameters": ["diagnosis_code"]},
        ),
    ],
)
def test_cost_filters_reject_unknown_invalid_and_repeated_values(query, details):
    response = fixture_app().test_client().get(f"/api/v1/costs/overview?{query}")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_QUERY_PARAMETER"
    assert response.get_json()["details"] == details
    assert "UNKNOWN" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ResultNotReadyError(), 503, "RESULT_NOT_READY"),
        (DatabaseUnavailableError(), 503, "DATABASE_UNAVAILABLE"),
        (InvalidServiceResultError(), 500, "SERVICE_RESULT_INVALID"),
    ],
)
def test_cost_base_dependency_failures_keep_stable_public_errors(error, status, code):
    class RaisingRepository:
        def fetch(self, module_key, entity_key):
            assert (module_key, entity_key) == (
                "costs",
                "diagnosis=*|facility=*|severity=*",
            )
            raise error

    response = fixture_app(analytics_repository=RaisingRepository()).test_client().get(
        "/api/v1/costs/overview"
    )

    assert response.status_code == status
    assert response.get_json()["code"] == code
    assert "diagnosis=*" not in response.get_data(as_text=True)


def test_cost_endpoint_rejects_body_and_non_get_methods():
    client = fixture_app().test_client()

    body = client.get(
        "/api/v1/costs/overview",
        data="{}",
        content_type="application/json",
    )
    assert body.status_code == 400
    assert body.get_json()["code"] == "INVALID_REQUEST_FORMAT"

    for method in ("post", "head", "options"):
        response = getattr(client, method)("/api/v1/costs/overview")
        assert response.status_code == 405
        if method != "head":
            assert response.get_json()["code"] == "METHOD_NOT_ALLOWED"


def test_valid_unpublished_filter_is_a_legal_empty_result():
    response = fixture_app().test_client().get(
        "/api/v1/cohorts/summary?age_group=50%20to%2069"
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["metrics"] == []

    risk = fixture_app().test_client().get("/api/v1/risks/overview?age_group=70%20or%20Older")
    assert risk.status_code == 200
    assert risk.get_json()["data"]["metrics"] == []


class RecordingCohortRepository:
    def __init__(self):
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "fixtures"
            / "analytics_snapshot_success.json"
        )
        self.delegate = FixtureAnalyticsSnapshotRepository(fixture_path)
        self.calls = []

    def fetch(self, module_key, entity_key):
        self.calls.append((module_key, entity_key))
        if module_key == "cohorts" and entity_key != "age=*|gender=*|admission=*":
            raise ResultNotReadyError()
        return self.delegate.fetch(module_key, entity_key)


def test_cohort_filters_use_frozen_order_and_return_legal_empty_results():
    repository = RecordingCohortRepository()
    response = fixture_app(analytics_repository=repository).test_client().get(
        "/api/v1/cohorts/summary?admission_type=Emergency&gender=F&age_group=50%20to%2069"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == {
        "age_group": "50 to 69",
        "gender": "F",
        "admission_type": "Emergency",
    }
    assert data["metrics"] == []
    assert data["sections"] == []
    assert repository.calls == [
        ("cohorts", "age=*|gender=*|admission=*"),
        ("cohorts", "age=50 to 69|gender=F|admission=Emergency"),
    ]


@pytest.mark.parametrize(
    ("query", "expected_filter"),
    [
        ("age_group=0%20to%2017", {"age_group": "0 to 17"}),
        ("gender=U", {"gender": "U"}),
        ("admission_type=Trauma", {"admission_type": "Trauma"}),
    ],
)
def test_each_cohort_filter_is_validated_against_published_options(
    query, expected_filter
):
    response = fixture_app().test_client().get(f"/api/v1/cohorts/summary?{query}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["filters"] == expected_filter
    assert data["metrics"] == []
    assert data["sections"] == []


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


def test_mysql_adapter_maps_database_failure_and_corrupt_json(monkeypatch):
    import pymysql

    config = {
        "MYSQL_HOST": "db",
        "MYSQL_USER": "reader",
        "MYSQL_DATABASE": "analytics",
    }
    repository = MySQLAnalyticsSnapshotRepository(config)

    def fail_connect(**kwargs):
        raise pymysql.MySQLError("password=secret should not escape")

    monkeypatch.setattr(pymysql, "connect", fail_connect)
    with pytest.raises(DatabaseUnavailableError):
        repository.fetch("dashboard", "overview")

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchone(self):
            return {
                "payload_json": "{not-json}",
                "data_version": "fixture:bad:v1",
                "generated_at": "2026-08-18T08:00:00.000000Z",
            }

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

        def close(self):
            return None

    connection = Connection()
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: connection)
    with pytest.raises(InvalidServiceResultError):
        repository.fetch("dashboard", "overview")
    assert connection.cursor_instance.params == ("dashboard", "overview")
    assert "analysis_snapshot_result" in connection.cursor_instance.query
