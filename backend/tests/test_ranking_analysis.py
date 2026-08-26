from __future__ import annotations

from app.services.ranking_analysis import analyze_evidence_ranking


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
