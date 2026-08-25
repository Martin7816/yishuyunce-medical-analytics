from __future__ import annotations

import pytest

from app.services.evidence_answer_generator import (
    ANSWER_STATUS_INSUFFICIENT_EVIDENCE,
    ANSWER_STATUS_OK,
    AnswerGroundingError,
    EVIDENCE_ANSWER_RESPONSE_FORMAT,
    EvidenceAnswerGenerator,
    EvidenceAnswerOutputError,
)


PROVENANCE = {
    "batch_id": "agg-test",
    "data_version": "fixture:aggregate:v1",
    "formula_version": "aggregate-additive-v1",
    "registry_version": "aggregate-registry-v1",
}


def ranking_evidence() -> dict[str, object]:
    return {
        "query_id": "query-evidence-1",
        "title": "Hospital ranking",
        "description": "Validated aggregate hospital case counts.",
        "metrics": [],
        "sections": [
            {
                "key": "hospital_ranking",
                "title": "Hospital ranking",
                "type": "bar",
                "items": [
                    {"name": "Hospital A", "value": 50},
                    {"name": "Hospital B", "value": 20},
                ],
            }
        ],
        "facts": [],
        "derived_facts": [],
        "provenance": PROVENANCE,
    }


def cohort_cost_evidence() -> dict[str, object]:
    return {
        "query_id": "query-cohort-cost-1",
        "title": "Medicare average charges",
        "description": "Validated aggregate payment cohort charges.",
        "metrics": [
            {
                "key": "avg_charges",
                "label": "Average charges",
                "value": 87975.991408,
            }
        ],
        "sections": [
            {
                "key": "aggregate_ranking",
                "title": "Average charges",
                "type": "bar",
                "items": [{"name": "Aggregate", "value": 87975.991408}],
            }
        ],
        "facts": [],
        "derived_facts": [],
        "provenance": PROVENANCE,
    }


def male_age_group_diagnosis_evidence() -> dict[str, object]:
    return {
        "query_id": "query-male-50-to-69-diagnosis",
        "title": "Diagnosis ranking by Age group / Gender / Diagnosis",
        "description": "Validated aggregate inpatient discharge record counts.",
        "metrics": [],
        "sections": [
            {
                "key": "diagnosis_ranking",
                "title": "Diagnosis ranking",
                "type": "bar",
                "items": [
                    {"name": "INF002 — SEPTICEMIA", "value": 26687},
                    {
                        "name": "INF012 — CORONAVIRUS DISEASE 2019 (COVID-19)",
                        "value": 17384,
                    },
                    {
                        "name": "MBD017 — ALCOHOL-RELATED DISORDERS",
                        "value": 14278,
                    },
                    {"name": "CIR019 — HEART FAILURE", "value": 11256},
                ],
            }
        ],
        "facts": [],
        "derived_facts": [],
        "query_scope_notes": [
            "筛选口径：50岁已按发布年龄组映射为50 to 69，无法提供精确到50岁的单岁统计；性别筛选为男性（M）。",
            "本结果统计住院出院记录中的病例量，不等同于一般人群患病率或个体患病风险。",
        ],
        "provenance": PROVENANCE,
    }


class FakeStructuredAnswerClient:
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


def make_generator(response: object) -> tuple[EvidenceAnswerGenerator, FakeStructuredAnswerClient]:
    client = FakeStructuredAnswerClient(response)
    return EvidenceAnswerGenerator(client), client


def grounded_response(text: str = "Hospital A has 50 cases.") -> dict[str, object]:
    return {
        "parsed": {
            "answer_text": text,
            "used_evidence_ids": ["query-evidence-1"],
        }
    }


def test_grounded_answer_is_returned_with_evidence_id_and_strict_output_format():
    generator, client = make_generator(grounded_response())

    result = generator.generate(
        "Which hospital has the highest case count?",
        ranking_evidence(),
        evidence_type="ranking",
    )

    assert result.status == ANSWER_STATUS_OK
    assert result.answer_text == "Hospital A has 50 cases."
    assert result.used_evidence_ids == ("query-evidence-1",)
    assert result.provenance == PROVENANCE
    assert client.calls[0][1] == EVIDENCE_ANSWER_RESPONSE_FORMAT
    assert "Hospital A" in client.calls[0][0][1]["content"]


def test_patient_cohort_aggregate_answer_is_allowed():
    response = grounded_response(
        "Medicare patients average charges are 87975.991408."
    )
    response["parsed"]["used_evidence_ids"] = ["query-cohort-cost-1"]
    generator, client = make_generator(response)

    result = generator.generate(
        "Medicare\u60a3\u8005\u5e73\u5747\u8d39\u7528\u662f\u591a\u5c11\uff1f",
        cohort_cost_evidence(),
        evidence_type="ranking",
    )

    assert result.status == ANSWER_STATUS_OK
    assert result.used_evidence_ids == ("query-cohort-cost-1",)
    assert result.provenance == PROVENANCE
    assert len(client.calls) == 1


def test_individual_patient_aggregate_request_is_rejected_before_provider_call():
    generator, client = make_generator(
        grounded_response("Average charges are 87975.991408.")
    )

    result = generator.generate(
        "\u67d0\u60a3\u8005\u8d39\u7528\u662f\u591a\u5c11\uff1f",
        cohort_cost_evidence(),
    )

    assert result.status == ANSWER_STATUS_INSUFFICIENT_EVIDENCE
    assert result.used_evidence_ids == ()
    assert result.provenance == PROVENANCE
    assert client.calls == []


def test_hallucinated_number_is_rejected():
    generator, _ = make_generator(
        grounded_response("Hospital A has 999 cases.")
    )

    with pytest.raises(AnswerGroundingError, match="number"):
        generator.generate("Which hospital has the highest case count?", ranking_evidence())


def test_nonexistent_measure_is_rejected_even_when_number_is_real():
    generator, _ = make_generator(
        grounded_response("Hospital A has an emergency rate of 50.")
    )

    with pytest.raises(AnswerGroundingError, match="measure"):
        generator.generate("Compare hospital metrics", ranking_evidence())


def test_missing_evidence_returns_insufficient_without_provider_call():
    generator, client = make_generator(grounded_response())

    result = generator.generate("Which hospital has the highest case count?", [])

    assert result.status == ANSWER_STATUS_INSUFFICIENT_EVIDENCE
    assert result.used_evidence_ids == ()
    assert result.provenance is None
    assert client.calls == []


def test_deterministic_fallback_summarizes_only_validated_evidence():
    generator, client = make_generator(grounded_response())

    result = generator.deterministic_fallback(
        "哪个医院病例量最高？",
        ranking_evidence(),
        evidence_type="ranking",
    )

    assert result.status == ANSWER_STATUS_OK
    assert "Hospital A" in result.answer_text
    assert "50" in result.answer_text
    assert "Hospital B" in result.answer_text
    assert result.used_evidence_ids == ("query-evidence-1",)
    assert client.calls == []


def test_deterministic_fallback_turns_cohort_ranking_into_client_ready_analysis():
    generator, client = make_generator(grounded_response())

    result = generator.deterministic_fallback(
        "50岁男性最容易得什么病？",
        male_age_group_diagnosis_evidence(),
        evidence_type="ranking",
    )

    assert result.status == ANSWER_STATUS_OK
    assert result.answer_text.startswith("结论：")
    assert "50–69岁男性" in result.answer_text
    assert "败血症" in result.answer_text
    assert "26,687" in result.answer_text
    assert "COVID-19" in result.answer_text
    assert "17,384" in result.answer_text
    assert "酒精相关障碍" in result.answer_text
    assert "14,278" in result.answer_text
    assert "住院主诊断记录" in result.answer_text
    assert "不等同于50岁个人的患病概率或医学诊断" in result.answer_text
    assert "query_plan" not in result.answer_text.casefold()
    assert "tool" not in result.answer_text.casefold()
    assert "thinking" not in result.answer_text.casefold()
    assert result.used_evidence_ids == ("query-male-50-to-69-diagnosis",)
    assert client.calls == []


def test_low_quality_model_ranking_is_replaced_by_client_ready_grounded_answer():
    generator, client = make_generator(
        {
            "parsed": {
                "answer_text": "INF002 — SEPTICEMIA: 26,687; INF012 — CORONAVIRUS DISEASE 2019 (COVID-19): 17,384.",
                "used_evidence_ids": ["query-male-50-to-69-diagnosis"],
            }
        }
    )

    result = generator.generate(
        "50岁男性最容易得什么病？",
        male_age_group_diagnosis_evidence(),
        evidence_type="ranking",
    )

    assert result.answer_text.startswith("结论：")
    assert "败血症" in result.answer_text
    assert "50–69岁男性" in result.answer_text
    assert "不等同于50岁个人的患病概率或医学诊断" in result.answer_text
    assert len(client.calls) == 1


def test_causal_wording_is_rejected():
    generator, _ = make_generator(
        grounded_response("Hospital A has 50 cases because it receives sicker patients.")
    )

    with pytest.raises(AnswerGroundingError, match="causal"):
        generator.generate("Compare hospital case counts", ranking_evidence())


def test_provenance_is_preserved_from_evidence_not_model_output():
    response = grounded_response()
    response["parsed"]["provenance"] = {"batch_id": "forged"}
    generator, _ = make_generator(response)

    with pytest.raises(EvidenceAnswerOutputError):
        generator.generate("Which hospital has the highest case count?", ranking_evidence())
