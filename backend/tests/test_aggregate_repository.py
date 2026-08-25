from __future__ import annotations

import json
import sys
from datetime import datetime

import pytest

from app import create_app  # noqa: E402

from app.repositories.aggregate import (  # noqa: E402
    DisabledAggregateRepository,
    MySQLAggregateFactRepository,
    build_aggregate_repository,
)
from app.errors import ServerMisconfiguredError  # noqa: E402


POLICY = {
    "policy_version": "query-suppression-v1",
    "mode": "query_time_final_group",
    "minimum_cohort_size": None,
    "secondary_suppression": True,
    "same_turn_differencing_protection": True,
    "fact_access": "internal_only",
}


def _batch_row():
    return {
        "batch_id": "agg_test",
        "data_version": "fixture:aggregate:v1",
        "formula_version": "aggregate-additive-v1",
        "registry_version": "aggregate-registry-v1",
        "suppression_policy_version": "query-suppression-v1",
        "suppression_policy_json": json.dumps(POLICY),
        "grain_json": json.dumps(
            ["facility_id", "diagnosis_code", "age", "gender", "severity", "payment", "admission"]
        ),
        "measures_json": json.dumps(
            [
                "record_count", "los_sum", "los_valid_count", "charges_sum",
                "charges_valid_count", "costs_sum", "costs_valid_count",
                "emergency_yes_count", "emergency_valid_count",
                "surgical_yes_count", "surgical_valid_count",
                "severe_yes_count", "severe_valid_count",
            ]
        ),
        "input_file_name": "sample.csv",
        "source_sha256": "c" * 64,
        "raw_records": 2,
        "source_records": 2,
        "aggregate_rows": 1,
        "status": "ACTIVE",
        "generated_at": datetime(2026, 8, 24),
        "validated_at": datetime(2026, 8, 24),
        "activated_at": datetime(2026, 8, 24),
    }


class FakeCursor:
    def __init__(self):
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, args=None):
        self.queries.append((query, args))

    def fetchone(self):
        return _batch_row()

    def fetchall(self):
        return [{"diagnosis_code": "RSP009", "record_count": 2}]


class FakeConnection:
    def __init__(self):
        self.cursor_value = FakeCursor()

    def cursor(self):
        return self.cursor_value

    def close(self):
        pass


class FakePyMySQL:
    MySQLError = Exception

    def __init__(self, connection):
        self.connection = connection

    def connect(self, **kwargs):
        return self.connection


class FakeCursors:
    DictCursor = object()


def test_missing_configuration_fails_closed():
    repository = build_aggregate_repository({})
    assert isinstance(repository, DisabledAggregateRepository)
    with pytest.raises(ServerMisconfiguredError):
        repository.fetch_active_batch()


def test_repository_uses_active_batch_and_server_side_group_by(monkeypatch):
    connection = FakeConnection()
    fake_mysql = FakePyMySQL(connection)
    monkeypatch.setitem(sys.modules, "pymysql", fake_mysql)
    monkeypatch.setitem(sys.modules, "pymysql.cursors", FakeCursors)
    repository = MySQLAggregateFactRepository(
        {
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": 3306,
            "MYSQL_USER": "test",
            "MYSQL_PASSWORD": "",
            "MYSQL_DATABASE": "test",
            "MYSQL_CONNECT_TIMEOUT": 3,
        }
    )

    result = repository.aggregate(
        group_by=("diagnosis_code",), filters={"gender": "F"}
    )
    assert result["batch"]["status"] == "ACTIVE"
    assert result["rows"] == [{"diagnosis_code": "RSP009", "record_count": 2}]
    aggregate_query = connection.cursor_value.queries[-1][0]
    assert "GROUP BY f.`diagnosis_code`" in aggregate_query
    assert aggregate_query.index("AND f.`gender`") < aggregate_query.index("GROUP BY")
    assert connection.cursor_value.queries[-1][1] == ("agg_test", "F")


def test_repository_separates_connect_and_read_timeout():
    repository = MySQLAggregateFactRepository(
        {
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": 3306,
            "MYSQL_USER": "test",
            "MYSQL_PASSWORD": "",
            "MYSQL_DATABASE": "test",
            "MYSQL_CONNECT_TIMEOUT": 3,
            "MYSQL_READ_TIMEOUT": 30,
        }
    )

    options = repository._connection_options()

    assert options["connect_timeout"] == 3
    assert options["read_timeout"] == 30
    assert options["write_timeout"] == 3


def test_repository_rejects_unknown_dimensions():
    repository = MySQLAggregateFactRepository({})
    with pytest.raises(ValueError, match="unknown aggregate dimensions"):
        repository.aggregate(group_by=("raw_patient_id",))


def test_aggregate_repository_remains_internal_only():
    app = create_app({"TESTING": True})
    assert all("aggregate" not in rule.rule for rule in app.url_map.iter_rules())
    repository = build_aggregate_repository({})
    assert not hasattr(repository, "fetch_raw")
