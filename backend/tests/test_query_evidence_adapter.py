from __future__ import annotations

import pytest

from app.services.query_evidence_adapter import (
    QueryEvidenceAdapter,
    QueryEvidenceAdapterError,
)
from shared.query_result_contract import QueryResultContract


PROVENANCE = {
    "batch_id": "agg-test",
    "data_version": "fixture:aggregate:v1",
    "formula_version": "aggregate-additive-v1",
    "registry_version": "aggregate-registry-v1",
}
METADATA = {
    "source": "analytics_aggregate_fact",
    "generated_at": "2026-08-25T00:00:00Z",
    "privacy_boundary": "aggregate_only",
}


def result_for(
    dimensions=("hospital",),
    measures=("case_count",),
    rows=(),
    limit=10,
):
    plan = {
        "version": "query_analytics-v1",
        "dimensions": list(dimensions),
        "measures": list(measures),
        "filters": [],
        "sort": [],
        "limit": limit,
    }
    return QueryResultContract(
        query_id="query-test",
        query_plan=plan,
        dimensions=tuple(dimensions),
        measures=tuple(measures),
        filters=(),
        rows=tuple(rows),
        row_count=len(rows),
        truncated=False,
        provenance=PROVENANCE,
        metadata=METADATA,
    )


def test_ranking_conversion_uses_query_rows():
    result = result_for(
        rows=(
            {"hospital": "Hospital B", "case_count": 20},
            {"hospital": "Hospital A", "case_count": 50},
        )
    )

    evidence = QueryEvidenceAdapter().adapt(result, "ranking")

    section = evidence["sections"][0]
    assert section["type"] == "bar"
    assert section["title"]
    assert section["visual"]["x_label"] == "Hospital"
    assert section["visual"]["y_label"] == "Case count"
    assert section["items"] == [
        {"name": "Hospital A", "value": 50},
        {"name": "Hospital B", "value": 20},
    ]
    assert evidence["facts"] == evidence["derived_facts"]


def test_provenance_is_preserved_in_evidence_and_chart():
    result = result_for(
        measures=("avg_los", "avg_charges"),
        rows=(
            {
                "hospital": "Hospital A",
                "avg_los": 4.2,
                "avg_charges": 9000.0,
            },
        ),
    )

    evidence = QueryEvidenceAdapter().adapt(result, "relationship")

    assert evidence["provenance"] == PROVENANCE
    assert evidence["chart"]["provenance"] == PROVENANCE
    assert evidence["chart"]["data_version"] == PROVENANCE["data_version"]


def test_fabricated_or_invalid_numeric_value_is_rejected():
    result = result_for(
        rows=({"hospital": "Hospital A", "case_count": 12},)
    ).to_document()
    result["rows"][0]["case_count"] = "999999"

    with pytest.raises(QueryEvidenceAdapterError):
        QueryEvidenceAdapter().adapt(result, "ranking")


def test_empty_result_is_safe_and_has_no_chart():
    evidence = QueryEvidenceAdapter().adapt(result_for(rows=()), "ranking")

    assert evidence["sections"][0]["items"] == []
    assert evidence["metrics"] == []
    assert evidence["facts"] == []
    assert evidence["chart"] is None


def test_chart_compatibility_for_comparison_distribution_and_relationship():
    comparison = QueryEvidenceAdapter().adapt(
        result_for(
            measures=("case_count", "avg_los"),
            rows=(
                {"hospital": "Hospital A", "case_count": 20, "avg_los": 3.0},
                {"hospital": "Hospital B", "case_count": 10, "avg_los": 5.0},
            ),
        ),
        "comparison",
    )
    distribution = QueryEvidenceAdapter().adapt(
        result_for(
            dimensions=("diagnosis",),
            rows=(
                {"diagnosis": "D1", "case_count": 20},
                {"diagnosis": "D2", "case_count": 10},
            ),
        ),
        "distribution",
    )
    relationship = QueryEvidenceAdapter().adapt(
        result_for(
            measures=("avg_los", "avg_charges"),
            rows=(
                {
                    "hospital": "Hospital A",
                    "avg_los": 3.0,
                    "avg_charges": 1000.0,
                },
                {
                    "hospital": "Hospital B",
                    "avg_los": 5.0,
                    "avg_charges": 2000.0,
                },
            ),
        ),
        "relationship",
    )

    assert comparison["chart"]["type"] == "grouped_bar"
    assert distribution["chart"]["type"] == "pie"
    assert relationship["chart"]["type"] == "scatter"


class StaticDiagnosisLabels:
    def __init__(self, labels, data_version):
        self.labels = labels
        self.data_version = data_version

    def resolve(self, code, data_version):
        if data_version != self.data_version:
            return None
        return self.labels.get(code)


def test_diagnosis_display_adds_name_without_changing_query_values():
    result = result_for(
        dimensions=("diagnosis",),
        rows=(
            {"diagnosis": "CIR019", "case_count": 20},
            {"diagnosis": "UNKNOWN", "case_count": 10},
        ),
    )
    evidence = QueryEvidenceAdapter(
        diagnosis_label_resolver=StaticDiagnosisLabels(
            {"CIR019": "HEART FAILURE"}, PROVENANCE["data_version"]
        )
    ).adapt(result, "ranking")

    assert evidence["sections"][0]["items"] == [
        {"name": "CIR019 — HEART FAILURE", "value": 20},
        {"name": "UNKNOWN", "value": 10},
    ]
    assert result.rows[0]["diagnosis"] == "CIR019"
    assert evidence["provenance"] == PROVENANCE


def test_diagnosis_display_falls_back_when_catalog_version_differs():
    result = result_for(
        dimensions=("diagnosis",),
        rows=({"diagnosis": "CIR019", "case_count": 20},),
    )
    evidence = QueryEvidenceAdapter(
        diagnosis_label_resolver=StaticDiagnosisLabels(
            {"CIR019": "HEART FAILURE"}, "different-version"
        )
    ).adapt(result, "ranking")

    assert evidence["sections"][0]["items"] == [
        {"name": "CIR019", "value": 20},
    ]
