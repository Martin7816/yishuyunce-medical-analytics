from __future__ import annotations

from app.services.query_intent import (
    infer_natural_language_intent,
    merge_query_plan_with_intent,
)


def test_exact_age_gender_disease_question_becomes_filtered_case_ranking():
    intent = infer_natural_language_intent("50岁男性最容易得什么病")

    assert intent.disease_case_ranking is True
    assert intent.dimensions == ("diagnosis",)
    assert intent.measures == ("case_count",)
    assert intent.filters == (
        {"dimension": "age_group", "operator": "eq", "value": "50 to 69"},
        {"dimension": "gender", "operator": "eq", "value": "M"},
    )
    assert "50岁" in intent.notes[0]
    assert "住院出院记录" in intent.notes[-1]


def test_range_and_female_phrasing_uses_published_age_bucket():
    intent = infer_natural_language_intent("50至69岁女性病例最多的疾病")

    assert intent.filters == (
        {"dimension": "age_group", "operator": "eq", "value": "50 to 69"},
        {"dimension": "gender", "operator": "eq", "value": "F"},
    )
    assert intent.notes == (
        "本结果统计住院出院记录中的病例量，不等同于一般人群患病率或个体患病风险",
    )


def test_age_upper_bound_keeps_all_matching_published_buckets():
    intent = infer_natural_language_intent("50岁以上男性病例最多的疾病")

    assert intent.filters[0] == {
        "dimension": "age_group",
        "operator": "in",
        "value": ["50 to 69", "70 or Older"],
    }
    assert "50岁以上" in intent.notes[0]


def test_plan_normalization_replaces_model_broad_age_and_measure_choice():
    plan = {
        "version": "query_analytics-v1",
        "dimensions": ["age_group", "diagnosis"],
        "measures": ["avg_los"],
        "filters": [
            {"dimension": "age_group", "operator": "eq", "value": "70 or Older"},
        ],
        "sort": [{"by": "avg_los", "direction": "desc"}],
        "limit": 10,
    }

    normalized = merge_query_plan_with_intent("50岁男性最容易得什么病", plan)

    assert normalized["dimensions"] == ["diagnosis"]
    assert normalized["measures"] == ["case_count"]
    assert normalized["filters"] == [
        {"dimension": "age_group", "operator": "eq", "value": "50 to 69"},
        {"dimension": "gender", "operator": "eq", "value": "M"},
    ]
    assert normalized["sort"] == [{"by": "case_count", "direction": "desc"}]


def test_generic_hospital_ranking_is_inferred_without_question_specific_branch():
    intent = infer_natural_language_intent("哪些医院病例量最高？")

    assert intent.disease_case_ranking is False
    assert intent.dimensions == ("hospital",)
    assert intent.measures == ("case_count",)
    assert intent.ranking_requested is True
    assert intent.filters == ()


def test_generic_measure_and_filter_are_inferred_for_payment_question():
    intent = infer_natural_language_intent("Medicare患者平均费用是多少？")

    assert intent.dimensions == ()
    assert intent.measures == ("avg_charges",)
    assert intent.filters == (
        {"dimension": "payment", "operator": "eq", "value": "Medicare"},
    )
    assert intent.has_structured_intent is True


def test_cross_dimension_distribution_is_inferred_as_a_supported_query_shape():
    intent = infer_natural_language_intent("不同性别疾病分布")

    assert intent.dimensions == ("diagnosis", "gender")
    assert intent.measures == ("case_count",)
    assert intent.distribution_requested is True
