from __future__ import annotations

from app.services.ranking_analysis import (
    analyze_cross_cube_ranking,
    analyze_evidence_ranking,
)


def ranking_evidence(*, measure="case_count", values=(16330, 15200, 12000)):
    return {
        "query_plan": {
            "version": "query_analytics-v1",
            "dimensions": ["hospital"],
            "measures": [measure],
            "filters": [],
            "sort": [{"by": measure, "direction": "desc"}],
            "limit": 3,
        },
        "sections": [
            {
                "key": "hospital_ranking",
                "title": "Ranking by Hospital",
                "type": "bar",
                "items": [
                    {"name": "Hospital A", "value": values[0]},
                    {"name": "Hospital B", "value": values[1]},
                    {"name": "Hospital C", "value": values[2]},
                ],
            }
        ],
    }


def test_ranking_analysis_derives_runner_up_gap_from_validated_rows():
    analysis = analyze_evidence_ranking(ranking_evidence(), "hospital")

    assert analysis is not None
    assert analysis.dimension == "hospital"
    assert analysis.measure == "case_count"
    assert analysis.measure_label == "病例量"
    assert analysis.unit == "条"
    assert [(item.label, item.value) for item in analysis.items] == [
        ("Hospital A", 16330),
        ("Hospital B", 15200),
        ("Hospital C", 12000),
    ]
    assert analysis.runner_up_gap == 1130
    assert analysis.returned_item_count == 3


def test_ranking_analysis_keeps_measure_semantics_for_cost_rankings():
    analysis = analyze_evidence_ranking(
        ranking_evidence(measure="avg_costs", values=(21000.5, 19000.0, 18000.0)),
        "hospital",
    )

    assert analysis is not None
    assert analysis.measure == "avg_costs"
    assert analysis.measure_label == "平均成本"
    assert analysis.unit == "美元"
    assert analysis.runner_up_gap == 2000.5


def test_ranking_analysis_does_not_invent_gap_for_one_returned_row():
    evidence = ranking_evidence(values=(16330, 15200, 12000))
    evidence["sections"][0]["items"] = evidence["sections"][0]["items"][:1]

    analysis = analyze_evidence_ranking(evidence, "hospital")

    assert analysis is not None
    assert analysis.runner_up_gap is None
    assert analysis.returned_item_count == 1


def test_cross_cube_analysis_recovers_structured_dimension_values() -> None:
    evidence = {
        "query_plan": {
            "version": "query_analytics-v1",
            "dimensions": ["age_group", "gender", "diagnosis"],
            "measures": ["case_count"],
            "filters": [],
            "sort": [{"by": "case_count", "direction": "desc"}],
            "limit": 10,
        },
        "sections": [
            {
                "key": "age_group_ranking",
                "type": "bar",
                "items": [
                    {
                        "name": "50 to 69 / M / INF002 — SEPTICEMIA",
                        "value": 26687,
                    },
                    {
                        "name": "70 or Older / F / CIR019 — HEART FAILURE",
                        "value": 11256,
                    },
                ],
            }
        ],
    }

    analysis = analyze_cross_cube_ranking(evidence)

    assert analysis is not None
    assert analysis.dimensions == ("age_group", "gender", "diagnosis")
    assert analysis.items[0].dimension_values == (
        ("age_group", "50 to 69"),
        ("gender", "M"),
        ("diagnosis", "INF002 — SEPTICEMIA"),
    )
    assert analysis.items[0].value == 26687
