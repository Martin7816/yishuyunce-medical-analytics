from __future__ import annotations

import copy

import pytest

from shared.query_result_contract import (
    QUERY_RESULT_SCHEMA,
    QueryResultContract,
    QueryResultContractError,
    validate_query_result,
)


def make_result(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "query_id": "query-test-1",
        "query_plan": {
            "version": "query_analytics-v1",
            "dimensions": ["age_group"],
            "measures": ["case_count"],
            "filters": [
                {
                    "dimension": "age_group",
                    "operator": "eq",
                    "value": "70 or Older",
                }
            ],
            "sort": [{"by": "case_count", "direction": "desc"}],
            "limit": 2,
        },
        "dimensions": ["age_group"],
        "measures": ["case_count"],
        "filters": [
            {
                "dimension": "age_group",
                "operator": "eq",
                "requested": "70 or Older",
                "resolved": "70 or Older",
                "resolution": "exact",
            }
        ],
        "rows": [{"age_group": "70 or Older", "case_count": 12}],
        "row_count": 1,
        "truncated": False,
        "provenance": {
            "batch_id": "agg-test",
            "data_version": "fixture:aggregate:v1",
            "formula_version": "aggregate-additive-v1",
            "registry_version": "aggregate-registry-v1",
        },
        "metadata": {
            "source": "analytics_aggregate_fact",
            "generated_at": "2026-08-25T00:00:00Z",
            "privacy_boundary": "aggregate_only",
        },
    }
    result.update(overrides)
    return result


def test_valid_result_is_normalized_and_future_evidence_ready():
    result = validate_query_result(make_result())

    assert isinstance(result, QueryResultContract)
    assert result.query_id == "query-test-1"
    assert result.row_count == 1
    assert result.provenance["batch_id"] == "agg-test"
    assert result.to_document()["metadata"]["privacy_boundary"] == "aggregate_only"
    assert result.to_document()["filters"][0]["resolution"] == "exact"


def test_missing_provenance_is_rejected():
    document = make_result()
    document.pop("provenance")

    with pytest.raises(QueryResultContractError, match="provenance"):
        validate_query_result(document)


def test_patient_field_is_rejected():
    document = make_result()
    document["rows"] = [
        {
            "age_group": "70 or Older",
            "case_count": 12,
            "patient_id": "patient-1",
        }
    ]

    with pytest.raises(QueryResultContractError, match="patient-level"):
        validate_query_result(document)


def test_row_overflow_is_rejected():
    document = make_result()
    document["rows"] = [
        {"age_group": "70 or Older", "case_count": 12},
        {"age_group": "50 to 69", "case_count": 8},
        {"age_group": "30 to 49", "case_count": 3},
    ]
    document["row_count"] = 3

    with pytest.raises(QueryResultContractError, match="limit"):
        validate_query_result(document)


def test_empty_result_is_legal():
    document = make_result(rows=[], row_count=0, truncated=False)

    result = validate_query_result(document)

    assert result.rows == ()
    assert result.row_count == 0


def test_invalid_measure_is_rejected():
    document = make_result()
    document["measures"] = ["patient_risk_score"]
    document["query_plan"] = copy.deepcopy(document["query_plan"])
    document["query_plan"]["measures"] = ["patient_risk_score"]
    document["rows"] = [{"age_group": "70 or Older", "patient_risk_score": 0.2}]

    with pytest.raises(QueryResultContractError, match="unknown"):
        validate_query_result(document)


def test_schema_is_strict_at_result_boundaries():
    assert QUERY_RESULT_SCHEMA["additionalProperties"] is False
    assert QUERY_RESULT_SCHEMA["properties"]["provenance"]["additionalProperties"] is False
    assert QUERY_RESULT_SCHEMA["properties"]["metadata"]["additionalProperties"] is False
    assert QUERY_RESULT_SCHEMA["properties"]["rows"]["items"]["additionalProperties"] is False
