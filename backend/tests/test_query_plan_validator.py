from __future__ import annotations

import pytest

from app.services.query_plan_validator import (
    QueryPlanValidationError,
    QueryPlanValidator,
)
from shared.query_plan_contract import QUERY_ANALYTICS_VERSION


def valid_plan() -> dict:
    return {
        "version": QUERY_ANALYTICS_VERSION,
        "dimensions": ["age_group", "diagnosis"],
        "measures": ["case_count"],
        "filters": [
            {
                "dimension": "age_group",
                "operator": "eq",
                "value": "70 or Older",
            }
        ],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 10,
    }


def test_valid_plan_is_accepted_as_immutable_contract():
    result = QueryPlanValidator().validate(valid_plan())

    assert result.version == QUERY_ANALYTICS_VERSION
    assert result.dimensions == ("age_group", "diagnosis")
    assert result.measures == ("case_count",)
    assert result.filters[0].value == "70 or Older"
    assert result.sort[0].by == "case_count"
    assert result.limit == 10


def test_unknown_dimension_is_rejected():
    plan = valid_plan()
    plan["dimensions"] = ["patient_group"]

    with pytest.raises(QueryPlanValidationError, match="unknown dimension"):
        QueryPlanValidator().validate(plan)


def test_unknown_measure_is_rejected():
    plan = valid_plan()
    plan["measures"] = ["patient_count"]

    with pytest.raises(QueryPlanValidationError, match="unknown measure"):
        QueryPlanValidator().validate(plan)


@pytest.mark.parametrize(
    "payload",
    [
        {"sql": "SELECT * FROM patients"},
        {"field": "facility_id"},
        {"expression": "record_count / 2"},
    ],
)
def test_injection_and_physical_query_payloads_are_rejected(payload):
    plan = valid_plan()
    plan.update(payload)

    with pytest.raises(QueryPlanValidationError):
        QueryPlanValidator().validate(plan)


def test_injection_in_filter_value_is_rejected():
    plan = valid_plan()
    plan["filters"][0]["value"] = "70 or Older' OR '1'='1"

    with pytest.raises(QueryPlanValidationError, match="unsafe query syntax"):
        QueryPlanValidator().validate(plan)


def test_limit_overflow_is_rejected():
    plan = valid_plan()
    plan["limit"] = 51

    with pytest.raises(QueryPlanValidationError, match="limit"):
        QueryPlanValidator().validate(plan)


@pytest.mark.parametrize(
    "invalid_filter",
    [
        {"dimension": "age_group", "operator": "contains", "value": "70"},
        {"dimension": "age_group", "operator": "eq"},
        {"dimension": "age_group", "operator": "eq", "value": ""},
        {"dimension": "age_group", "operator": "eq", "value": 70},
        {
            "dimension": "age_group",
            "operator": "in",
            "value": ["70", "70"],
        },
    ],
)
def test_invalid_filter_is_rejected(invalid_filter):
    plan = valid_plan()
    plan["filters"] = [invalid_filter]

    with pytest.raises(QueryPlanValidationError):
        QueryPlanValidator().validate(plan)


def test_additional_properties_are_rejected_at_nested_boundaries():
    plan = valid_plan()
    plan["filters"][0]["field"] = "age"

    with pytest.raises(QueryPlanValidationError, match="forbidden query plan field"):
        QueryPlanValidator().validate(plan)
