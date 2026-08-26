from __future__ import annotations

from datetime import datetime

import pytest

from app.errors import ResultNotReadyError
from app.repositories.aggregate_query import (
    AggregateQueryValidationError,
    MySQLAggregateQueryRepository,
    QueryResultContract,
)
from app.services.safe_query_compiler import (
    CompiledAggregateQuery,
    CompiledFilter,
    SafeQueryCompiler,
)
from shared.query_plan_contract import SortSpec


def make_plan(**overrides: object) -> dict[str, object]:
    plan: dict[str, object] = {
        "version": "query_analytics-v1",
        "dimensions": ["age_group", "diagnosis"],
        "measures": ["case_count", "avg_los", "emergency_rate"],
        "filters": [
            {
                "dimension": "age_group",
                "operator": "eq",
                "value": "70 or Older",
            }
        ],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 2,
    }
    plan.update(overrides)
    return plan


def _active_batch() -> dict[str, str | datetime]:
    return {
        "batch_id": "agg_test",
        "data_version": "fixture:aggregate:v1",
        "formula_version": "aggregate-additive-v1",
        "registry_version": "aggregate-registry-v1",
        "status": "ACTIVE",
    }


class FakeBatchRepository:
    def __init__(self, batch: dict[str, object] | None = None, error=None):
        self.batch = batch
        self.error = error

    def fetch_active_batch(self):
        if self.error is not None:
            raise self.error
        return self.batch if self.batch is not None else _active_batch()


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_value = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


def _repository(rows):
    connection = FakeConnection(rows)
    repository = MySQLAggregateQueryRepository(
        {
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_USER": "test",
            "MYSQL_DATABASE": "test",
        },
        active_batch_repository=FakeBatchRepository(),
        connection_factory=lambda: connection,
    )
    return repository, connection


def _compiled_query(**overrides: object) -> CompiledAggregateQuery:
    return SafeQueryCompiler().compile(make_plan(**overrides))


def test_valid_aggregate_query_uses_one_fact_table_and_bound_values():
    repository, connection = _repository(
        [
            {
                "age_group": "70 or Older",
                "diagnosis": "RSP009",
                "case_count": 12,
                "avg_los": 3.5,
                "emergency_rate": 0.25,
            }
        ]
    )

    result = repository.execute(_compiled_query())

    assert isinstance(result, QueryResultContract)
    assert result.rows[0]["case_count"] == 12
    assert "FROM `analytics_aggregate_fact` AS f" in connection.cursor_value.query
    assert "JOIN" not in connection.cursor_value.query.upper()
    assert "analytics_aggregate_batch" not in connection.cursor_value.query
    assert "analytics_aggregate_active_batch" not in connection.cursor_value.query
    assert connection.cursor_value.params == (
        "agg_test",
        "PNL001",
        "70 or Older",
        2,
    )


def test_diagnosis_rankings_exclude_server_owned_non_disease_codes():
    repository, connection = _repository([])
    query = _compiled_query(
        dimensions=["diagnosis"],
        measures=["case_count"],
        filters=[],
        sort=[{"by": "case_count", "direction": "desc"}],
        limit=10,
    )

    repository.execute(query)

    assert "f.`diagnosis_code` NOT IN (%s)" in connection.cursor_value.query
    assert connection.cursor_value.params == ("agg_test", "PNL001", 10)


def test_unknown_field_is_rejected():
    query = _compiled_query()
    invalid = CompiledAggregateQuery(
        dimensions=("raw_patient_id",),
        measures=query.measures,
        filters=(),
        order_by=(),
        limit=2,
        source_capability="aggregate_raw_patient_id",
    )
    repository, _ = _repository([])

    with pytest.raises(AggregateQueryValidationError, match="unknown aggregate dimension"):
        repository.execute(invalid)


def test_active_batch_missing_is_rejected():
    repository, _ = _repository([])
    repository._active_batch_repository = FakeBatchRepository(
        error=ResultNotReadyError("active aggregate batch")
    )

    with pytest.raises(ResultNotReadyError):
        repository.execute(_compiled_query())


def test_filter_injection_is_rejected():
    query = _compiled_query()
    invalid_filter = CompiledFilter(
        dimension="age_group",
        operator="eq",
        requested="70 or Older' OR '1'='1",
        resolved="70 or Older' OR '1'='1",
        resolution="exact",
    )
    invalid = CompiledAggregateQuery(
        dimensions=query.dimensions,
        measures=query.measures,
        filters=(invalid_filter,),
        order_by=query.order_by,
        limit=query.limit,
        source_capability=query.source_capability,
    )
    repository, _ = _repository([])

    with pytest.raises(AggregateQueryValidationError, match="unsafe query syntax"):
        repository.execute(invalid)


def test_provenance_is_attached_to_result():
    repository, _ = _repository(
        [
            {
                "age_group": "70 or Older",
                "diagnosis": "RSP009",
                "case_count": 12,
                "avg_los": 3.5,
                "emergency_rate": 0.25,
            }
        ]
    )

    result = repository.execute(_compiled_query())

    assert result.batch_id == "agg_test"
    assert result.data_version == "fixture:aggregate:v1"
    assert result.formula_version == "aggregate-additive-v1"
    assert result.registry_version == "aggregate-registry-v1"
    assert result.provenance == {
        "batch_id": "agg_test",
        "data_version": "fixture:aggregate:v1",
        "formula_version": "aggregate-additive-v1",
        "registry_version": "aggregate-registry-v1",
    }


def test_row_limit_is_enforced_in_sql_and_result():
    repository, connection = _repository(
        [
            {
                "age_group": "70 or Older",
                "diagnosis": "RSP009",
                "case_count": index,
                "avg_los": 3.5,
                "emergency_rate": 0.25,
            }
            for index in range(5)
        ]
    )

    result = repository.execute(_compiled_query())

    assert len(result.rows) == 2
    assert "LIMIT %s" in connection.cursor_value.query
    assert connection.cursor_value.params[-1] == 2
