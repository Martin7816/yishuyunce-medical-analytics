from __future__ import annotations

import pytest

from app.services.safe_query_compiler import (
    SafeQueryCompiler,
    SafeQueryCompilerError,
    UnsupportedCapabilityError,
)


def make_plan(**overrides: object) -> dict[str, object]:
    plan: dict[str, object] = {
        "version": "query_analytics-v1",
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
    plan.update(overrides)
    return plan


def test_valid_compile_returns_repository_neutral_query() -> None:
    compiled = SafeQueryCompiler().compile(make_plan())

    assert compiled.dimensions == ("age_group", "diagnosis")
    assert compiled.measures == ("case_count",)
    assert compiled.filters[0].resolved == "70 or Older"
    assert compiled.filters[0].resolution == "exact"
    assert compiled.order_by[0].by == "case_count"
    assert compiled.limit == 10
    assert compiled.source_capability == "aggregate_age_group_diagnosis"
    assert "field" not in compiled.to_document()
    assert "sql" not in compiled.to_document()
    assert "table" not in compiled.to_document()


def test_unknown_dimension_is_rejected() -> None:
    with pytest.raises(SafeQueryCompilerError, match="unknown dimension"):
        SafeQueryCompiler().compile(
            make_plan(dimensions=["age_group", "not_a_dimension"])
        )


def test_unsupported_dimension_combination_is_rejected() -> None:
    with pytest.raises(UnsupportedCapabilityError, match="unsupported aggregate"):
        SafeQueryCompiler().compile(
            make_plan(dimensions=["hospital", "diagnosis"])
        )


def test_invalid_measure_is_rejected() -> None:
    with pytest.raises(SafeQueryCompilerError, match="unknown measure"):
        SafeQueryCompiler().compile(make_plan(measures=["not_a_measure"]))


def test_injection_payload_is_rejected_before_compilation() -> None:
    with pytest.raises(SafeQueryCompilerError, match="unsafe query syntax"):
        SafeQueryCompiler().compile(
            make_plan(
                filters=[
                    {
                        "dimension": "age_group",
                        "operator": "eq",
                        "value": "70 or Older' OR '1'='1",
                    }
                ]
            )
        )


def test_age_granularity_fallback_is_explicit() -> None:
    compiled = SafeQueryCompiler().compile(
        make_plan(
            filters=[
                {
                    "dimension": "age_group",
                    "operator": "eq",
                    "value": "80+",
                }
            ]
        )
    )

    filter_result = compiled.filters[0]
    assert filter_result.requested == "80+"
    assert filter_result.resolved == "70 or Older"
    assert filter_result.value == "70 or Older"
    assert filter_result.resolution == "coarsened"
