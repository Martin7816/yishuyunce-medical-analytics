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
