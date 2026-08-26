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
    ranking_fact = evidence["derived_facts"][0]
    assert ranking_fact["runner_up_gap"] == 30
    assert ranking_fact["returned_total"] == 70
    assert ranking_fact["coverage"] == "top_k"
    assert "total" not in ranking_fact
    assert all("share" not in item for item in ranking_fact["top"])
    assert evidence["facts"] == evidence["derived_facts"]


def test_filtered_question_adds_coarsening_and_case_count_scope_notes():
    result = result_for(
        dimensions=("diagnosis",),
        rows=({"diagnosis": "D1", "case_count": 20},),
    )

    evidence = QueryEvidenceAdapter().adapt(
        result,
        "ranking",
        question="50岁男性最容易得什么病",
    )

    assert evidence["query_scope_notes"] == [
        "筛选口径：50岁已按发布年龄组映射为50 to 69，无法提供精确到50岁的单岁统计；性别筛选为男性（M）",
        "本结果统计住院出院记录中的病例量，不等同于一般人群患病率或个体患病风险",
    ]
    assert evidence["query_scope_notes"][0] in evidence["limitations"]


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
    distribution_fact = distribution["derived_facts"][0]
    assert distribution_fact["coverage"] == "complete_distribution"
    assert distribution_fact["total"] == 30
    assert distribution_fact["top"][0]["share"] == pytest.approx(2 / 3, abs=1e-6)


class StaticDiagnosisLabels:
    def __init__(self, labels, data_version):
        self.labels = labels
        self.data_version = data_version

    def resolve(self, code, data_version):
        if data_version != self.data_version:
            return None
        return self.labels.get(code)


class StaticHospitalLabels:
    def __init__(self, labels, data_version):
        self.labels = labels
        self.data_version = data_version

    def resolve(self, code, data_version):
        if data_version != self.data_version:
            return None
        return self.labels.get(code)


def test_hospital_display_adds_name_without_changing_query_values():
    result = result_for(
        rows=(
            {"hospital": "000541", "case_count": 16330},
            {"hospital": "000123", "case_count": 12000},
        ),
    )
    evidence = QueryEvidenceAdapter(
        hospital_label_resolver=StaticHospitalLabels(
            {"000541": "North Shore University Hospital"},
            PROVENANCE["data_version"],
        )
    ).adapt(result, "ranking")

    assert evidence["sections"][0]["items"] == [
        {"name": "North Shore University Hospital（机构编码：000541）", "value": 16330},
        {"name": "医院 000123", "value": 12000},
    ]
    assert result.rows[0]["hospital"] == "000541"
    assert evidence["provenance"] == PROVENANCE


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
