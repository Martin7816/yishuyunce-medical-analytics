from __future__ import annotations

from app.services.ai_chart import build_chart_from_evidence


VERSION = "sparcs_2021_20231012_sha256_test"


def source(tool: str, sections: list[dict], metrics: list[dict] | None = None) -> dict:
    return {
        "tool": tool,
        "title": "Validated analytics",
        "data_version": VERSION,
        "metrics": metrics if metrics is not None else [{"key": "fallback", "label": "Fallback metric", "value": 205}],
        "sections": sections,
        "derived_facts": [{"key": "not_chart_source", "value": 999999}],
    }


def test_hospital_case_ranking_beats_unrelated_first_section_and_keeps_section_values():
    evidence = source(
        "get_hospital_overview",
        [
            {
                "key": "facility_metric_comparison",
                "title": "Facility comparison",
                "type": "grouped_bar",
                "items": [{"category": "Case count", "series": [{"key": "a", "label": "A", "value": 205}]}],
            },
            {
                "key": "ranking",
                "title": "Hospital case count ranking",
                "type": "bar",
                "items": [
                    {"name": "Mount Sinai Hospital", "value": 49945},
                    {"name": "North Shore University Hospital", "value": 49203},
                ],
            },
        ],
    )

    chart = build_chart_from_evidence("Which hospitals have the highest case count?", [evidence])

    assert chart is not None
    assert chart["source_section"] == "ranking"
    assert chart["type"] == "bar"
    assert chart["items"] == [
        {"name": "Mount Sinai Hospital", "value": 49945},
        {"name": "North Shore University Hospital", "value": 49203},
    ]
    assert chart["items"][0]["value"] != evidence["derived_facts"][0]["value"]
    assert chart["data_version"] == VERSION


def test_relationship_question_selects_scatter_section():
    evidence = source(
        "get_hospital_overview",
        [
            {
                "key": "ranking",
                "title": "Hospital ranking",
                "type": "bar",
                "items": [{"name": "Hospital A", "value": 100}],
            },
            {
                "key": "facility_relation",
                "title": "Length of stay and charges relationship",
                "type": "scatter",
                "visual": {"x_label": "Length of stay", "y_label": "Charges"},
                "items": [{"name": "Hospital A", "x": 5.4, "y": 81242.3, "size": 49945}],
            },
        ],
    )

    chart = build_chart_from_evidence(
        "What is the relationship between hospital length of stay and charges?",
        [evidence],
    )

    assert chart is not None
    assert chart["type"] == "scatter"
    assert chart["source_section"] == "facility_relation"
    assert chart["items"][0]["x"] == 5.4
    assert chart["items"][0]["y"] == 81242.3


def test_cost_distribution_selects_quantiles_and_risk_structure_selects_heatmap():
    cost = source(
        "get_cost_overview",
        [
            {"key": "severity", "title": "Charges by severity", "type": "bar", "items": [{"name": "Major", "value": 100}]},
            {"key": "quantiles", "title": "Charge distribution", "type": "bar", "items": [{"name": "P90", "value": 162403.2}]},
        ],
    )
    risk = source(
        "get_risk_overview",
        [
            {"key": "severity", "title": "Severity distribution", "type": "bar", "items": [{"name": "Major", "value": 100}]},
            {
                "key": "age_severity_matrix",
                "title": "Age and severity structure",
                "type": "heatmap",
                "visual": {"x_label": "Age", "y_label": "Severity"},
                "items": [{"x_label": "70 or Older", "y_label": "Extreme", "value": 87802}],
            },
        ],
    )

    cost_chart = build_chart_from_evidence("How is the charge distribution?", [cost])
    risk_chart = build_chart_from_evidence("What is the high-risk population structure?", [risk])

    assert cost_chart is not None
    assert cost_chart["source_section"] == "quantiles"
    assert risk_chart is not None
    assert risk_chart["source_section"] == "age_severity_matrix"
    assert risk_chart["type"] == "heatmap"


def test_metrics_are_only_a_fallback_when_no_visual_section_is_available():
    evidence = source(
        "get_dashboard_overview",
        [],
        metrics=[{"key": "facility_count", "label": "Analyzable facilities", "value": 205}],
    )

    chart = build_chart_from_evidence("Summarize the current operation", [evidence])

    assert chart == {
        "type": "bar",
        "title": "Validated analytics来源指标",
        "items": [{"name": "Analyzable facilities", "value": 205}],
        "source_tool": "get_dashboard_overview",
        "data_version": VERSION,
        "source_metric_keys": ["facility_count"],
    }


def test_no_sections_and_no_metrics_returns_no_chart():
    evidence = source("get_dashboard_overview", [], metrics=[])
    assert build_chart_from_evidence("Summarize the current operation", [evidence]) is None
