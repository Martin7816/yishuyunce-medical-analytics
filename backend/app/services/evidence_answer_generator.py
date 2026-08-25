"""Generate answers that are grounded in the existing Safe Evidence contract.

This module is a separate backend flow boundary.  It does not alter the
legacy conversation service or stream responses.  The model receives a
server-labelled, JSON-serialized evidence envelope and must return a
provider-parsed structured answer.  Numeric and semantic safety checks are
performed again after the model response; provenance is always copied from
the evidence by the server.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .ai_evidence import (
    assess_question_scope,
    is_simple_conversation,
    is_patient_level_question,
    validate_answer_grounding,
)


SUPPORTED_EVIDENCE_TYPES = frozenset(
    {"ranking", "comparison", "distribution", "relationship"}
)
ANSWER_STATUS_OK = "ok"
ANSWER_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
_ANSWER_STATUSES = frozenset(
    {ANSWER_STATUS_OK, ANSWER_STATUS_INSUFFICIENT_EVIDENCE}
)
_PROVENANCE_FIELDS = frozenset(
    {"batch_id", "data_version", "formula_version", "registry_version"}
)
_ANSWER_FIELDS = frozenset({"answer_text", "used_evidence_ids"})


EVIDENCE_ANSWER_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "evidence_grounded_answer_v1",
        "strict": True,
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "evidence_grounded_answer-v1",
            "type": "object",
            "additionalProperties": False,
            "required": ["answer_text", "used_evidence_ids"],
            "properties": {
                "answer_text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                },
                "used_evidence_ids": {
                    "type": "array",
                    "maxItems": 50,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                    },
                },
            },
        },
    },
}


GROUNDED_ANSWER_SYSTEM_PROMPT = """You are an evidence-grounded medical operations analytics answerer.
The user question and the labelled evidence are the only permitted sources.
Return exactly one JSON object matching evidence_grounded_answer_v1.
Use only numbers, measures, categories, comparisons, distributions, rankings,
and relationships present in the supplied evidence. Cite every evidence block
used through used_evidence_ids.

The exact response shape is:
{"answer_text":"A concise answer using only supplied evidence.","used_evidence_ids":["the supplied evidence_id"]}
Return only these two keys. Do not add answer, data_version, evidence_grounded,
limitations, provenance, or any other key; provenance is attached by the server.

Never invent or estimate a number, metric, category, ranking, or data version.
For rankings, copy only the category/value pairs present in the supplied rows.
Never calculate or add totals, shares, percentages, gaps, differences, or other
derived numbers, even when they could be computed from the rows.
When the evidence contains a filtered diagnosis ranking, answer that ranking
directly instead of refusing merely because patient-level detail is absent.
Respect query_scope_notes and mention their age-group or record-count caveat
briefly when it matters. Treat “病例量” as the number of inpatient discharge
records; do not call it prevalence, incidence, or an individual's disease risk.
Never infer causality or use causal explanations. Never give a diagnosis,
treatment, medication, medical recommendation, or patient-level conclusion.
If the evidence does not support the question, return a concise insufficient
evidence statement and an empty used_evidence_ids array. Do not return prose
outside the structured object.
"""


_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
)
_CAUSAL_PATTERN = re.compile(
    r"(?:"
    r"\b(?:because|cause|caused|causal|causality|due to|leads? to|results? in|"
    r"drives?|explains?|responsible for|as a result|therefore|impact(?:s|ed)?)\b"
    r"|因为|由于|原因|导致|因果|归因|影响|造成|所以|因此"
    r")",
    re.IGNORECASE,
)
_MEDICAL_OR_PATIENT_PATTERN = re.compile(
    r"(?:"
    r"\b(?:treatment|medication|prescription|diagnose|diagnosis advice|"
    r"medical advice|mrn|ssn)\b"
    r"|个人级|个人明细|治疗|用药|处方|医嘱|诊疗建议|医疗建议|诊断建议"
    r")",
    re.IGNORECASE,
)
_INSUFFICIENT_PATTERN = re.compile(
    r"(?:"
    r"\binsufficient evidence\b|\bnot enough evidence\b|\bno evidence\b|"
    r"\bcannot determine\b|\bnot supported by the evidence\b"
    r"|证据不足|缺少证据|无法确定|无法回答|不支持"
    r")",
    re.IGNORECASE,
)
_SECTION_TYPE_TO_ANALYSIS = {
    "bar": "ranking",
    "grouped_bar": "comparison",
    "pie": "distribution",
    "scatter": "relationship",
}
_NON_GENERIC_MEASURE_PHRASES = (
    "average length of stay",
    "length of stay",
    "avg_los",
    "average charges",
    "charges",
    "average costs",
    "costs",
    "emergency rate",
    "surgical rate",
    "severe rate",
    "readmission rate",
    "mortality rate",
    "rate",
    "percentage",
    "share",
)
_MEASURE_ANCHORS = {
    "case_count": ("case count", "cases", "number of cases"),
    "avg_los": ("average length of stay", "length of stay", "avg_los"),
    "avg_charges": ("average charges", "charges", "avg_charges"),
    "avg_costs": ("average costs", "costs", "avg_costs"),
    "emergency_rate": ("emergency rate", "emergency_rate"),
    "surgical_rate": ("surgical rate", "surgical_rate"),
    "severe_rate": ("severe rate", "severe_rate"),
}


@runtime_checkable
class StructuredAnswerClientProtocol(Protocol):
    """Provider boundary for native structured answer generation."""

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_format: Mapping[str, Any],
    ) -> object:
        """Return a provider-parsed structured answer object or envelope."""


class EvidenceAnswerGeneratorError(ValueError):
    """Base error for fail-closed answer generation."""


class EvidenceAnswerOutputError(EvidenceAnswerGeneratorError):
    """The provider did not return the strict answer contract."""


class AnswerGroundingError(EvidenceAnswerGeneratorError):
    """The answer contains unsupported facts or unsafe conclusions."""


class EvidenceInputError(EvidenceAnswerGeneratorError):
    """The supplied evidence cannot be used as a Safe Evidence source."""


@dataclass(frozen=True, slots=True)
class AnswerResult:
    """Server-owned result of one evidence-grounded answer attempt."""

    status: str
    answer_text: str
    used_evidence_ids: tuple[str, ...]
    provenance: dict[str, str] | None

    def __post_init__(self) -> None:
        if self.status not in _ANSWER_STATUSES:
            raise ValueError(f"unsupported answer status: {self.status}")
        if not isinstance(self.answer_text, str) or not self.answer_text.strip():
            raise ValueError("answer_text must be a non-empty string")
        if not isinstance(self.used_evidence_ids, tuple):
            raise ValueError("used_evidence_ids must be a tuple")
        if len(set(self.used_evidence_ids)) != len(self.used_evidence_ids):
            raise ValueError("used_evidence_ids must not contain duplicates")
        if self.status == ANSWER_STATUS_OK and not self.used_evidence_ids:
            raise ValueError("a grounded answer must cite evidence")
        if self.status == ANSWER_STATUS_INSUFFICIENT_EVIDENCE and self.used_evidence_ids:
            raise ValueError("insufficient evidence answers must not cite evidence")
        if self.provenance is not None and not isinstance(self.provenance, dict):
            raise ValueError("provenance must be an object or null")

    def to_document(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "answer_text": self.answer_text,
            "used_evidence_ids": list(self.used_evidence_ids),
            "provenance": dict(self.provenance) if self.provenance is not None else None,
        }


def _as_evidence_list(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if not all(isinstance(item, Mapping) for item in value):
            raise EvidenceInputError("safe evidence items must be objects")
        return list(value)
    raise EvidenceInputError("safe evidence must be an object or an array")


def _validate_provenance(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise EvidenceInputError("evidence provenance must be an object")
    if set(value) != set(_PROVENANCE_FIELDS):
        raise EvidenceInputError("evidence provenance has an invalid shape")
    normalized: dict[str, str] = {}
    for field in _PROVENANCE_FIELDS:
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise EvidenceInputError(f"evidence provenance.{field} must be non-empty")
        if _CONTROL_CHARACTER_PATTERN.search(item):
            raise EvidenceInputError(f"evidence provenance.{field} contains control characters")
        normalized[field] = item
    return normalized


def _evidence_identifier(
    evidence: Mapping[str, Any], index: int, existing: set[str]
) -> str:
    candidate: object = evidence.get("evidence_id")
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = evidence.get("query_id")
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = evidence.get("id")
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = f"evidence-{index + 1}"

    normalized = candidate.strip()
    if len(normalized) > 256 or _CONTROL_CHARACTER_PATTERN.search(normalized):
        raise EvidenceInputError("evidence identifier is invalid")
    base = normalized
    suffix = 2
    while normalized in existing:
        normalized = f"{base}#{suffix}"
        suffix += 1
    return normalized


def _has_evidence_content(evidence: Mapping[str, Any]) -> bool:
    metrics = evidence.get("metrics")
    if isinstance(metrics, Sequence) and not isinstance(metrics, (str, bytes)):
        if any(isinstance(item, Mapping) and "value" in item for item in metrics):
            return True

    for key in ("facts", "derived_facts"):
        facts = evidence.get(key)
        if isinstance(facts, Sequence) and not isinstance(facts, (str, bytes)):
            if any(isinstance(item, Mapping) and item for item in facts):
                return True

    sections = evidence.get("sections")
    if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            items = section.get("items")
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                if any(isinstance(item, Mapping) and item for item in items):
                    return True
    return False


def _number_tokens(text: str) -> list[float]:
    values: list[float] = []
    for match in _NUMBER_PATTERN.findall(text):
        normalized = match.replace(",", "").rstrip("%")
        try:
            values.append(float(normalized))
        except ValueError:
            continue
    return values


def _evidence_numbers(value: object, *, key: str | None = None) -> list[float]:
    """Collect numbers only from fact-bearing Safe Evidence fields."""

    if key not in {"metrics", "sections", "facts", "derived_facts"}:
        if isinstance(value, Mapping):
            numbers: list[float] = []
            for child_key, child_value in value.items():
                if child_key in {"metrics", "sections", "facts", "derived_facts"}:
                    numbers.extend(_evidence_numbers(child_value, key=child_key))
            return numbers
        return []
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return _number_tokens(value)
    if isinstance(value, Mapping):
        numbers = []
        for child_value in value.values():
            numbers.extend(_evidence_numbers(child_value, key=key))
        return numbers
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        numbers = []
        for child_value in value:
            numbers.extend(_evidence_numbers(child_value, key=key))
        return numbers
    return []


def _number_is_grounded(value: float, evidence_values: Sequence[float]) -> bool:
    for source in evidence_values:
        candidates = (source, source * 100.0)
        for candidate in candidates:
            tolerance = max(0.02, abs(candidate) * 0.005)
            if abs(value - candidate) <= tolerance:
                return True
    return False


def _evidence_text(evidence: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(
        list(evidence),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).casefold()


def _evidence_anchors(evidence: Sequence[Mapping[str, Any]]) -> set[str]:
    """Return user-visible labels that can ground a natural-language answer."""

    anchors: set[str] = set()
    for item in evidence:
        raw = item.get("evidence", item)
        if not isinstance(raw, Mapping):
            continue
        for key in ("tool", "title", "description"):
            value = raw.get(key)
            if isinstance(value, str) and len(value.strip()) >= 2:
                anchors.add(value.strip().casefold())
        for key in ("metrics", "sections", "facts", "derived_facts"):
            values = raw.get(key)
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                continue
            for value in values:
                if not isinstance(value, Mapping):
                    continue
                for field in (
                    "key",
                    "label",
                    "title",
                    "name",
                    "category",
                    "x_label",
                    "y_label",
                    "unit",
                ):
                    text = value.get(field)
                    if isinstance(text, str) and len(text.strip()) >= 2:
                        anchors.add(text.strip().casefold())
                if key == "sections":
                    section_items = value.get("items")
                    if isinstance(section_items, Sequence) and not isinstance(
                        section_items, (str, bytes)
                    ):
                        for section_item in section_items:
                            if not isinstance(section_item, Mapping):
                                continue
                            for field in (
                                "name",
                                "category",
                                "x_label",
                                "y_label",
                            ):
                                text = section_item.get(field)
                                if isinstance(text, str) and len(text.strip()) >= 2:
                                    anchors.add(text.strip().casefold())
                            series = section_item.get("series")
                            if isinstance(series, Sequence) and not isinstance(
                                series, (str, bytes)
                            ):
                                for series_item in series:
                                    if not isinstance(series_item, Mapping):
                                        continue
                                    for field in ("key", "label"):
                                        text = series_item.get(field)
                                        if isinstance(text, str) and len(text.strip()) >= 2:
                                            anchors.add(text.strip().casefold())
                visual = value.get("visual")
                if isinstance(visual, Mapping):
                    for field in ("x_label", "y_label", "unit"):
                        text = visual.get(field)
                        if isinstance(text, str) and len(text.strip()) >= 2:
                            anchors.add(text.strip().casefold())
                for field in ("source_metric_keys",):
                    source_keys = value.get(field)
                    if isinstance(source_keys, Sequence) and not isinstance(
                        source_keys, (str, bytes)
                    ):
                        anchors.update(
                            text.casefold()
                            for text in source_keys
                            if isinstance(text, str) and len(text) >= 2
                        )

        serialized = json.dumps(raw, ensure_ascii=False, sort_keys=True).casefold()
        for measure_id, aliases in _MEASURE_ANCHORS.items():
            if measure_id in serialized:
                anchors.update(aliases)
    return anchors


def _validate_semantic_grounding(
    answer: str,
    cited_evidence: Sequence[Mapping[str, Any]],
) -> None:
    lowered_answer = answer.casefold()
    serialized_evidence = _evidence_text(cited_evidence)
    for phrase in _NON_GENERIC_MEASURE_PHRASES:
        if phrase in lowered_answer and phrase not in serialized_evidence:
            raise AnswerGroundingError(
                f"answer contains a measure not present in evidence: {phrase}"
            )

    anchors = _evidence_anchors(cited_evidence)
    if not any(anchor in lowered_answer for anchor in anchors):
        raise AnswerGroundingError("answer does not identify a cited evidence fact")


def _extract_answer_document(response: object) -> Mapping[str, Any]:
    """Extract parsed output only; never parse a free-text ``content`` field."""

    if not isinstance(response, Mapping):
        raise EvidenceAnswerOutputError("structured answer response must be an object")
    if "answer_text" in response:
        return response

    for key in ("parsed", "structured_output", "output", "json_schema", "json"):
        candidate = response.get(key)
        if isinstance(candidate, Mapping):
            return candidate
        if candidate is not None:
            raise EvidenceAnswerOutputError(
                f"structured answer response field {key} must be an object"
            )

    choices = response.get("choices")
    if isinstance(choices, list) and len(choices) == 1:
        choice = choices[0]
        if isinstance(choice, Mapping):
            message = choice.get("message")
            if isinstance(message, Mapping):
                for key in ("parsed", "structured_output", "json_schema", "json"):
                    candidate = message.get(key)
                    if isinstance(candidate, Mapping):
                        return candidate
                    if candidate is not None:
                        raise EvidenceAnswerOutputError(
                            f"structured answer message field {key} must be an object"
                        )

    raise EvidenceAnswerOutputError(
        "answer response did not contain a provider-parsed structured object"
    )


def _insufficient_result(provenance: dict[str, str] | None) -> AnswerResult:
    return AnswerResult(
        status=ANSWER_STATUS_INSUFFICIENT_EVIDENCE,
        answer_text="Insufficient evidence to answer this question from the supplied aggregate evidence.",
        used_evidence_ids=(),
        provenance=dict(provenance) if provenance is not None else None,
    )


def _fallback_number(value: object) -> str | None:
    """Format a number without deriving, rounding, or inventing a value."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def _fallback_text_parts(
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str]]:
    """Extract display lines from Safe Evidence without model interpretation."""

    lines: list[str] = []
    used_ids: list[str] = []

    for item in prepared:
        evidence_id = item.get("evidence_id")
        raw = item.get("evidence")
        if not isinstance(evidence_id, str) or not isinstance(raw, Mapping):
            continue

        local_lines: list[str] = []
        sections = raw.get("sections")
        if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
            for section in sections:
                if not isinstance(section, Mapping):
                    continue
                section_items = section.get("items")
                if not isinstance(section_items, Sequence) or isinstance(
                    section_items, (str, bytes)
                ):
                    continue
                for section_item in section_items[:10]:
                    if not isinstance(section_item, Mapping):
                        continue
                    label = section_item.get("name", section_item.get("category"))
                    if not isinstance(label, str) or not label.strip():
                        label = "Aggregate"
                    label = label.strip()
                    series = section_item.get("series")
                    if isinstance(series, Sequence) and not isinstance(
                        series, (str, bytes)
                    ):
                        values: list[str] = []
                        for series_item in series[:6]:
                            if not isinstance(series_item, Mapping):
                                continue
                            value = _fallback_number(series_item.get("value"))
                            series_label = series_item.get("label", series_item.get("key"))
                            if value is None or not isinstance(series_label, str):
                                continue
                            values.append(f"{series_label.strip()}={value}")
                        if values:
                            local_lines.append(f"{label}: {', '.join(values)}")
                        continue
                    value = _fallback_number(section_item.get("value"))
                    if value is not None:
                        local_lines.append(f"{label}: {value}")

        if not local_lines:
            metrics = raw.get("metrics")
            if isinstance(metrics, Sequence) and not isinstance(metrics, (str, bytes)):
                for metric in metrics[:10]:
                    if not isinstance(metric, Mapping):
                        continue
                    value = _fallback_number(metric.get("value"))
                    label = metric.get("label", metric.get("key"))
                    if value is not None and isinstance(label, str) and label.strip():
                        local_lines.append(f"{label.strip()}: {value}")

        if not local_lines:
            facts = raw.get("derived_facts", raw.get("facts"))
            if isinstance(facts, Sequence) and not isinstance(facts, (str, bytes)):
                for fact in facts[:10]:
                    if not isinstance(fact, Mapping):
                        continue
                    value = _fallback_number(fact.get("value"))
                    label = fact.get("label", fact.get("key"))
                    if value is not None and isinstance(label, str) and label.strip():
                        local_lines.append(f"{label.strip()}: {value}")

        if local_lines:
            used_ids.append(evidence_id)
            lines.extend(local_lines)

    return lines[:10], used_ids


def _deterministic_fallback_result(
    question: str,
    prepared: Sequence[Mapping[str, Any]],
    provenance: dict[str, str] | None,
) -> AnswerResult:
    lines, used_ids = _fallback_text_parts(prepared)
    if not lines or not used_ids:
        return _insufficient_result(provenance)

    notes: list[str] = []
    for item in prepared:
        raw = item.get("evidence")
        if not isinstance(raw, Mapping):
            continue
        for key in ("query_scope_notes", "limitations"):
            values = raw.get(key)
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                continue
            for value in values:
                if isinstance(value, str) and value.strip() and value.strip() not in notes:
                    notes.append(value.strip())

    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    if is_chinese:
        answer = "根据已核验的汇总数据：" + "；".join(lines) + "。"
        if notes:
            answer += "口径说明：" + "；".join(notes[:2])
    else:
        answer = "Based on the validated aggregate evidence: " + "; ".join(lines) + "."
        if notes:
            answer += " Scope notes: " + "; ".join(notes[:2])

    return AnswerResult(
        status=ANSWER_STATUS_OK,
        answer_text=answer,
        used_evidence_ids=tuple(dict.fromkeys(used_ids)),
        provenance=dict(provenance) if provenance is not None else None,
    )


def _append_required_scope_notes(
    answer: str,
    question: str,
    cited_evidence: Sequence[Mapping[str, Any]],
) -> str:
    """Attach server-owned query scope even when the model omits it."""

    notes: list[str] = []
    for item in cited_evidence:
        raw = item.get("evidence", item)
        if not isinstance(raw, Mapping):
            continue
        values = raw.get("query_scope_notes")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        for value in values:
            if (
                isinstance(value, str)
                and value.strip()
                and len(value.strip()) <= 500
                and not _CONTROL_CHARACTER_PATTERN.search(value)
                and value.strip() not in notes
            ):
                notes.append(value.strip())

    missing = [note for note in notes if note not in answer]
    if not missing:
        return answer
    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    prefix = "口径说明：" if is_chinese else "Scope notes: "
    separator = "；" if is_chinese else "; "
    scoped_answer = f"{answer.rstrip()}\n\n{prefix}{separator.join(missing)}"
    if len(scoped_answer) > 4000:
        raise AnswerGroundingError("answer and required scope notes are too long")
    return scoped_answer


class EvidenceAnswerGenerator:
    """Generate one grounded answer from one or more Safe Evidence blocks."""

    def __init__(
        self,
        client: StructuredAnswerClientProtocol | object,
        *,
        system_prompt: str = GROUNDED_ANSWER_SYSTEM_PROMPT,
    ) -> None:
        if client is None:
            raise ValueError("structured answer client is required")
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt must be a non-empty string")
        self.client = client
        self.system_prompt = system_prompt

    def _prepare_evidence(
        self,
        safe_evidence: object,
    ) -> tuple[list[dict[str, Any]], dict[str, str] | None, bool]:
        raw_items = _as_evidence_list(safe_evidence)
        prepared: list[dict[str, Any]] = []
        known_ids: set[str] = set()
        provenance: dict[str, str] | None = None
        has_content = False

        for index, item in enumerate(raw_items):
            item_provenance = _validate_provenance(item.get("provenance"))
            if item_provenance is not None:
                if provenance is None:
                    provenance = item_provenance
                elif provenance != item_provenance:
                    raise EvidenceInputError("evidence provenance values do not match")

            evidence_id = _evidence_identifier(item, index, known_ids)
            known_ids.add(evidence_id)
            has_content = has_content or _has_evidence_content(item)
            prepared.append(
                {
                    "evidence_id": evidence_id,
                    "evidence": deepcopy(dict(item)),
                }
            )

        if has_content and provenance is None:
            raise EvidenceInputError("usable evidence must include provenance")
        return prepared, provenance, has_content

    def _messages(
        self,
        question: str,
        evidence: Sequence[Mapping[str, Any]],
        evidence_type: str | None,
    ) -> list[dict[str, str]]:
        payload = {
            "question": question,
            "requested_analysis": evidence_type,
            "evidence": list(evidence),
        }
        return [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ]

    def _complete_structured(
        self,
        messages: list[dict[str, str]],
        response_format: Mapping[str, Any],
    ) -> object:
        complete_structured = getattr(self.client, "complete_structured", None)
        if not callable(complete_structured):
            raise EvidenceAnswerOutputError(
                "answer client must expose complete_structured(messages, response_format)"
            )
        try:
            return complete_structured(messages, response_format)
        except EvidenceAnswerGeneratorError:
            raise
        except Exception as error:
            raise EvidenceAnswerOutputError("structured answer request failed") from error

    @staticmethod
    def _validate_answer_document(
        document: Mapping[str, Any],
        known_ids: set[str],
        cited_evidence: list[Mapping[str, Any]],
    ) -> tuple[str, tuple[str, ...]]:
        if set(document) != set(_ANSWER_FIELDS):
            raise EvidenceAnswerOutputError(
                "answer must contain exactly answer_text and used_evidence_ids"
            )

        answer = document.get("answer_text")
        if not isinstance(answer, str) or not answer.strip():
            raise EvidenceAnswerOutputError("answer_text must be a non-empty string")
        answer = answer.strip()
        if len(answer) > 4000:
            raise EvidenceAnswerOutputError("answer_text is too long")
        if _CONTROL_CHARACTER_PATTERN.search(answer):
            raise EvidenceAnswerOutputError("answer_text contains control characters")

        raw_ids = document.get("used_evidence_ids")
        if not isinstance(raw_ids, list):
            raise EvidenceAnswerOutputError("used_evidence_ids must be an array")
        if len(raw_ids) > 50:
            raise EvidenceAnswerOutputError("used_evidence_ids contains too many items")
        if any(
            not isinstance(item, str) or not item.strip() for item in raw_ids
        ):
            raise EvidenceAnswerOutputError("used_evidence_ids must contain text IDs")
        used_ids = tuple(item.strip() for item in raw_ids)
        if len(set(used_ids)) != len(used_ids):
            raise EvidenceAnswerOutputError("used_evidence_ids must not contain duplicates")
        unknown = set(used_ids) - known_ids
        if unknown:
            raise EvidenceAnswerOutputError(
                f"answer cites unknown evidence id: {sorted(unknown)[0]}"
            )

        if not used_ids and _INSUFFICIENT_PATTERN.search(answer):
            return answer, used_ids
        if not used_ids:
            raise AnswerGroundingError("grounded answers must cite supplied evidence")

        if _CAUSAL_PATTERN.search(answer):
            raise AnswerGroundingError("causal wording is not permitted")
        if is_patient_level_question(answer) or _MEDICAL_OR_PATIENT_PATTERN.search(answer):
            raise AnswerGroundingError(
                "medical advice and patient-level conclusions are not permitted"
            )

        cited_values: list[float] = []
        for item in cited_evidence:
            cited_values.extend(_evidence_numbers(item.get("evidence", item)))
        for value in _number_tokens(answer):
            if not _number_is_grounded(value, cited_values):
                raise AnswerGroundingError(
                    f"answer contains a number not present in evidence: {value:g}"
                )

        _validate_semantic_grounding(answer, cited_evidence)

        answerability = {"status": "answerable"}
        cited_documents = [
            item.get("evidence", item)
            for item in cited_evidence
            if isinstance(item.get("evidence", item), Mapping)
        ]
        if not validate_answer_grounding(answer, cited_documents, answerability):
            raise AnswerGroundingError("answer is not grounded in cited evidence")
        return answer, used_ids

    def generate(
        self,
        question: str,
        safe_evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        evidence_type: str | None = None,
    ) -> AnswerResult:
        """Generate a grounded answer, or return an insufficient-evidence result."""

        if not isinstance(question, str) or not question.strip():
            raise EvidenceAnswerGeneratorError("question must be a non-empty string")
        normalized_question = question.strip()
        if len(normalized_question) > 1000:
            raise EvidenceAnswerGeneratorError("question is too long")
        if evidence_type is not None and evidence_type not in SUPPORTED_EVIDENCE_TYPES:
            raise EvidenceAnswerGeneratorError(
                f"unsupported evidence type: {evidence_type}"
            )

        prepared, provenance, has_content = self._prepare_evidence(safe_evidence)
        if not prepared or not has_content:
            return _insufficient_result(provenance)

        scope = assess_question_scope(normalized_question)
        if scope is not None or is_simple_conversation(normalized_question):
            return _insufficient_result(provenance)
        if (
            _CAUSAL_PATTERN.search(normalized_question)
            or is_patient_level_question(normalized_question)
            or _MEDICAL_OR_PATIENT_PATTERN.search(normalized_question)
        ):
            return _insufficient_result(provenance)

        known_ids = {item["evidence_id"] for item in prepared}
        response_format = deepcopy(EVIDENCE_ANSWER_RESPONSE_FORMAT)
        response = self._complete_structured(
            self._messages(normalized_question, prepared, evidence_type),
            response_format,
        )
        document = _extract_answer_document(response)

        raw_ids = document.get("used_evidence_ids") if isinstance(document, Mapping) else None
        cited_ids = set(raw_ids) if isinstance(raw_ids, list) else set()
        cited_evidence = [
            item for item in prepared if item["evidence_id"] in cited_ids
        ]
        answer, used_ids = self._validate_answer_document(
            document,
            known_ids,
            cited_evidence,
        )
        if not used_ids and _INSUFFICIENT_PATTERN.search(answer):
            return _insufficient_result(provenance)
        answer = _append_required_scope_notes(
            answer,
            normalized_question,
            cited_evidence,
        )
        return AnswerResult(
            status=ANSWER_STATUS_OK,
            answer_text=answer,
            used_evidence_ids=used_ids,
            provenance=dict(provenance) if provenance is not None else None,
        )

    def deterministic_fallback(
        self,
        question: str,
        safe_evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        evidence_type: str | None = None,
    ) -> AnswerResult:
        """Answer from server-owned evidence when the model answer fails.

        This is intentionally a summary fallback, not a second language
        model.  It lets the API remain useful during a provider timeout while
        preserving the same evidence IDs and provenance as the normal path.
        """

        if not isinstance(question, str) or not question.strip():
            raise EvidenceAnswerGeneratorError("question must be a non-empty string")
        normalized_question = question.strip()
        if evidence_type is not None and evidence_type not in SUPPORTED_EVIDENCE_TYPES:
            raise EvidenceAnswerGeneratorError(
                f"unsupported evidence type: {evidence_type}"
            )
        prepared, provenance, has_content = self._prepare_evidence(safe_evidence)
        if not prepared or not has_content:
            return _insufficient_result(provenance)
        scope = assess_question_scope(normalized_question)
        if (
            scope is not None
            or is_simple_conversation(normalized_question)
            or is_patient_level_question(normalized_question)
            or _CAUSAL_PATTERN.search(normalized_question)
            or _MEDICAL_OR_PATIENT_PATTERN.search(normalized_question)
        ):
            return _insufficient_result(provenance)
        return _deterministic_fallback_result(
            normalized_question,
            prepared,
            provenance,
        )

    def generate_answer(
        self,
        question: str,
        safe_evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        evidence_type: str | None = None,
    ) -> AnswerResult:
        """Compatibility alias for callers using answer terminology."""

        return self.generate(
            question,
            safe_evidence,
            evidence_type=evidence_type,
        )

    def answer(
        self,
        question: str,
        safe_evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        evidence_type: str | None = None,
    ) -> AnswerResult:
        return self.generate(
            question,
            safe_evidence,
            evidence_type=evidence_type,
        )


__all__ = [
    "ANSWER_STATUS_INSUFFICIENT_EVIDENCE",
    "ANSWER_STATUS_OK",
    "AnswerGroundingError",
    "AnswerResult",
    "EVIDENCE_ANSWER_RESPONSE_FORMAT",
    "EvidenceAnswerGenerator",
    "EvidenceAnswerGeneratorError",
    "EvidenceAnswerOutputError",
    "EvidenceInputError",
    "GROUNDED_ANSWER_SYSTEM_PROMPT",
    "SUPPORTED_EVIDENCE_TYPES",
    "StructuredAnswerClientProtocol",
]
