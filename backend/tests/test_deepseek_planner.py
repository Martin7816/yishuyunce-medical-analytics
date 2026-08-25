from __future__ import annotations

import json

import pytest

from app.services.deepseek_planner import (
    DEEPSEEK_PLANNER_RESPONSE_FORMAT,
    DeepSeekPlannerAdapter,
    PlannerOutputValidationError,
    PlannerProviderError,
    StructuredOutputError,
    UnsupportedPlannerIntent,
)
from shared.query_plan_contract import QUERY_ANALYTICS_VERSION


def valid_plan() -> dict[str, object]:
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


class FakeStructuredClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, object],
    ) -> object:
        self.calls.append((messages, response_format))
        return self.response


class FailingStructuredClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or RuntimeError("provider unavailable")
        self.calls = 0

    def complete_structured(self, messages, response_format):
        self.calls += 1
        raise self.error


def make_planner(response: object) -> tuple[DeepSeekPlannerAdapter, FakeStructuredClient]:
    client = FakeStructuredClient(response)
    return DeepSeekPlannerAdapter(client), client


def test_valid_planner_response_returns_validated_query_plan_and_strict_schema():
    planner, client = make_planner({"parsed": valid_plan()})

    result = planner.generate_plan("Show hospital case counts by age group")

    assert result.to_document() == valid_plan()
    assert len(client.calls) == 1
    response_format = client.calls[0][1]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == DEEPSEEK_PLANNER_RESPONSE_FORMAT[
        "json_schema"
    ]["schema"]
    assert client.calls[0][0][1]["content"] == (
        "Show hospital case counts by age group"
    )


def test_chinese_filtered_disease_question_is_normalized_before_validation():
    planner, client = make_planner({"parsed": valid_plan()})

    result = planner.generate_plan("50岁男性最容易得什么病")

    assert result.to_document() == {
        "version": QUERY_ANALYTICS_VERSION,
        "dimensions": ["diagnosis"],
        "measures": ["case_count"],
        "filters": [
            {"dimension": "age_group", "operator": "eq", "value": "50 to 69"},
            {"dimension": "gender", "operator": "eq", "value": "M"},
        ],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 10,
    }
    assert client.calls[0][0][1]["content"] == "50岁男性最容易得什么病"


def test_patient_cohort_aggregate_question_is_allowed_for_planning():
    planner, client = make_planner({"parsed": valid_plan()})

    result = planner.generate_plan(
        "Medicare\u60a3\u8005\u5e73\u5747\u8d39\u7528\u662f\u591a\u5c11\uff1f"
    )

    assert result.to_document() == {
        "version": QUERY_ANALYTICS_VERSION,
        "dimensions": [],
        "measures": ["avg_charges"],
        "filters": [
            {"dimension": "payment", "operator": "eq", "value": "Medicare"}
        ],
        "sort": [],
        "limit": 10,
    }
    assert len(client.calls) == 1


def test_individual_patient_question_is_rejected_before_planning():
    planner, client = make_planner({"parsed": valid_plan()})

    with pytest.raises(UnsupportedPlannerIntent):
        planner.generate_plan("\u67d0\u60a3\u8005\u8d39\u7528\u662f\u591a\u5c11\uff1f")

    assert client.calls == []


def test_free_text_or_malformed_json_is_rejected_without_json_parsing():
    planner, client = make_planner({"content": json.dumps(valid_plan())})

    with pytest.raises(StructuredOutputError, match="structured"):
        planner.generate_plan("Show hospital case counts")

    assert len(client.calls) == 1


def test_schema_violation_is_fail_closed():
    invalid = valid_plan()
    invalid["sql"] = "SELECT * FROM patients"
    planner, _ = make_planner({"parsed": invalid})

    with pytest.raises(PlannerOutputValidationError):
        planner.generate_plan("Show hospital case counts")


def test_sql_injection_question_is_rejected_before_provider_call():
    planner, client = make_planner({"parsed": valid_plan()})

    with pytest.raises(UnsupportedPlannerIntent, match="forbidden"):
        planner.generate_plan("SELECT * FROM patient WHERE hospital = 'A';")

    assert client.calls == []


def test_unsupported_question_is_fail_closed_before_provider_call():
    planner, client = make_planner({"parsed": valid_plan()})

    with pytest.raises(UnsupportedPlannerIntent, match="supported aggregate"):
        planner.generate_plan("What is the weather today?")

    assert client.calls == []


def test_provider_failure_recovers_with_bounded_deterministic_plan():
    client = FailingStructuredClient()
    planner = DeepSeekPlannerAdapter(client)

    result = planner.generate_plan("哪些医院病例量最高？")

    assert result.to_document() == {
        "version": QUERY_ANALYTICS_VERSION,
        "dimensions": ["hospital"],
        "measures": ["case_count"],
        "filters": [],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 10,
    }
    assert client.calls == 1


def test_provider_error_type_remains_a_structured_output_error():
    assert issubclass(PlannerProviderError, StructuredOutputError)
