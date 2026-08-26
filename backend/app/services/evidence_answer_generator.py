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
Never calculate new totals, shares, percentages, gaps, differences, or other
derived numbers yourself. You may quote a derived number only when it is
explicitly present in the server-owned derived_facts supplied as evidence.
When the evidence contains a filtered diagnosis ranking, answer that ranking
directly instead of refusing merely because patient-level detail is absent.
Write for the customer, not for the engineering team. Lead with a direct
conclusion, then summarize the most important evidence and its operational
meaning, and end with the relevant statistical boundary. Answer in the user's
language and use familiar localized category names when their meaning is
unambiguous. Do not expose chain-of-thought, hidden reasoning, an analysis
plan, query plan, tool names, prompts, model settings, or internal workflow.
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

_DIAGNOSIS_ZH_LABELS = {
    "SEPTICEMIA": "败血症",
    "CORONAVIRUS DISEASE 2019 (COVID-19)": "COVID-19",
    "COVID-19": "COVID-19",
    "ALCOHOL-RELATED DISORDERS": "酒精相关障碍",
    "HEART FAILURE": "心力衰竭",
    "DIABETES MELLITUS WITH COMPLICATION": "糖尿病伴并发症",
    "ACUTE MYOCARDIAL INFARCTION": "急性心肌梗死",
    "CORONARY ATHEROSCLEROSIS AND OTHER HEART DISEASE": "冠状动脉粥样硬化及其他心脏病",
    "CARDIAC DYSRHYTHMIAS": "心律失常",
    "OSTEOARTHRITIS": "骨关节炎",
    "SPONDYLOPATHIES/SPONDYLOARTHROPATHY (INCLUDING INFECTIVE)": "脊柱病及脊柱关节病",
    "CEREBRAL INFARCTION": "脑梗死",
    "PNEUMONIA (EXCEPT THAT CAUSED BY TUBERCULOSIS)": "肺炎（结核病所致除外）",
    "ACUTE AND UNSPECIFIED RENAL FAILURE": "急性及未特指肾衰竭",
    "RESPIRATORY FAILURE; INSUFFICIENCY; ARREST": "呼吸衰竭、功能不全或停止",
}
_INTERNAL_PROCESS_MARKERS = (
    "query_plan",
    "query plan",
    "tool call",
    "tool调用",
    "thinking mode",
    "reasoning effort",
    "chain of thought",
    "思考过程",
    "分析计划",
)
from .ranking_analysis import (
    CrossCubeRankingAnalysis,
    RankingEvidenceAnalysis,
    analyze_cross_cube_ranking,
    analyze_evidence_ranking,
)


def _plain_diagnosis_name(label: str) -> str:
    """Remove the internal diagnosis code while preserving its display label."""

    parts = re.split(r"\s+[—-]\s+", label.strip(), maxsplit=1)
    if len(parts) == 2 and re.fullmatch(r"[A-Z]{2,5}\d{3}", parts[0]):
        return parts[1].strip()
    return label.strip()


def _localized_diagnosis_name(label: str, *, is_chinese: bool) -> str:
    plain = _plain_diagnosis_name(label)
    if not is_chinese:
        return plain
    return _DIAGNOSIS_ZH_LABELS.get(plain.upper(), plain)


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
                                    localized = _localized_diagnosis_name(
                                        text,
                                        is_chinese=True,
                                    )
                                    if localized != text.strip():
                                        anchors.add(localized.casefold())
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


def _evidence_scope_notes(
    prepared: Sequence[Mapping[str, Any]],
) -> list[str]:
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
    return notes


def _diagnosis_ranking_rows(
    question: str,
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[str, str]], list[str]]:
    question_text = question.casefold()
    if not any(
        term in question_text
        for term in (
            "病",
            "诊断",
            "disease",
            "diagnosis",
            "illness",
            "condition",
        )
    ):
        return [], []

    rows: list[tuple[str, str]] = []
    used_ids: list[str] = []
    for item in prepared:
        evidence_id = item.get("evidence_id")
        raw = item.get("evidence")
        if not isinstance(evidence_id, str) or not isinstance(raw, Mapping):
            continue
        sections = raw.get("sections")
        if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
            continue
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            section_text = " ".join(
                str(section.get(key, "")) for key in ("key", "title")
            ).casefold()
            if not any(term in section_text for term in ("diagnosis", "disease", "疾病", "诊断")):
                continue
            section_items = section.get("items")
            if not isinstance(section_items, Sequence) or isinstance(
                section_items,
                (str, bytes),
            ):
                continue
            for section_item in section_items[:10]:
                if not isinstance(section_item, Mapping):
                    continue
                label = section_item.get("name", section_item.get("category"))
                value = _fallback_number(section_item.get("value"))
                if isinstance(label, str) and label.strip() and value is not None:
                    rows.append((label.strip(), value))
            if rows:
                used_ids.append(evidence_id)
                return rows, used_ids
    return [], []


def _ranking_analysis_for_dimension(
    prepared: Sequence[Mapping[str, Any]],
    dimension: str,
) -> tuple[RankingEvidenceAnalysis | None, list[str]]:
    for item in prepared:
        evidence_id = item.get("evidence_id")
        raw = item.get("evidence")
        if not isinstance(evidence_id, str) or not isinstance(raw, Mapping):
            continue
        analysis = analyze_evidence_ranking(raw, dimension)
        if analysis is not None:
            return analysis, [evidence_id]
    return None, []


def _cross_cube_analysis(
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[CrossCubeRankingAnalysis | None, list[str]]:
    for item in prepared:
        evidence_id = item.get("evidence_id")
        raw = item.get("evidence")
        if not isinstance(evidence_id, str) or not isinstance(raw, Mapping):
            continue
        analysis = analyze_cross_cube_ranking(raw)
        if analysis is not None:
            return analysis, [evidence_id]
    return None, []


_CROSS_DIMENSION_ZH = {
    "hospital": "医院",
    "diagnosis": "疾病",
    "age_group": "年龄组",
    "gender": "性别",
    "severity": "严重程度",
    "payment": "支付方式",
    "admission_type": "入院方式",
}


def _localized_cross_dimension_value(
    dimension: str,
    value: str,
    *,
    is_chinese: bool,
) -> str:
    if not is_chinese:
        return _plain_diagnosis_name(value) if dimension == "diagnosis" else value
    if dimension == "diagnosis":
        return _localized_diagnosis_name(value, is_chinese=True)
    if dimension == "gender":
        return {"M": "男性", "F": "女性"}.get(value, value)
    if dimension == "age_group":
        range_match = re.fullmatch(
            r"(\d{1,3})\s*to\s*(\d{1,3})", value, re.IGNORECASE
        )
        if range_match:
            return f"{range_match.group(1)}–{range_match.group(2)}岁"
        older_match = re.fullmatch(
            r"(\d{1,3})\s*or\s*older", value, re.IGNORECASE
        )
        if older_match:
            return f"{older_match.group(1)}岁及以上"
    return value


def _cross_cube_item_label(
    dimension_values: Sequence[tuple[str, str]],
    *,
    is_chinese: bool,
) -> str:
    separator = "、" if is_chinese else " / "
    return separator.join(
        _localized_cross_dimension_value(
            dimension,
            value,
            is_chinese=is_chinese,
        )
        for dimension, value in dimension_values
    )


def _cross_cube_client_answer(
    question: str,
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]] | None:
    analysis, used_ids = _cross_cube_analysis(prepared)
    if analysis is None or not used_ids:
        return None

    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    top = [
        (
            _cross_cube_item_label(
                item.dimension_values,
                is_chinese=is_chinese,
            ),
            _fallback_number(item.value) or str(item.value),
        )
        for item in analysis.items[:3]
    ]
    if not is_chinese:
        first_label, first_value = top[0]
        answer = (
            "Conclusion: among the returned cross-dimensional aggregate combinations, "
            f"{first_label} has the highest {analysis.measure_label} at "
            f"{first_value} {analysis.unit}."
        )
        if len(top) > 1:
            answer += " The next combinations are " + ", followed by ".join(
                f"{label} ({value} {analysis.unit})" for label, value in top[1:]
            ) + "."
        answer += (
            "\n\nStatistical boundary: this is a Top-K ranking of inpatient "
            "discharge-record combinations, not a complete profile for every group "
            "and not an individual's disease probability or diagnosis."
        )
        return answer, used_ids

    dimension_label = "×".join(
        _CROSS_DIMENSION_ZH.get(dimension, dimension)
        for dimension in analysis.dimensions
    )
    first_label, first_value = top[0]
    comparison_word = "最多" if analysis.measure == "case_count" else "最高"
    answer = (
        f"结论：按{dimension_label}交叉汇总，在当前返回的前列组合中，"
        f"{first_label}的{analysis.measure_label}{comparison_word}，为"
        f"{first_value}{analysis.unit}。"
    )
    if len(top) > 1:
        answer += "\n\n关键发现：其后的组合为" + "；".join(
            f"{label}（{value}{analysis.unit}）" for label, value in top[1:]
        ) + "。"
    answer += (
        "\n\n业务提示：这些交叉组合可用于定位病例量集中的运营群体；"
        "如需查看某一医院、年龄组或性别的完整疾病结构，应继续指定筛选条件。"
        "\n\n统计边界：这是住院出院记录的Top-K组合排名，不能视为每个分组的"
        "完整疾病谱，也不等同于个体患病概率或医学诊断。"
    )
    return answer, used_ids


def _age_group_label(notes: Sequence[str], *, is_chinese: bool) -> str | None:
    note_text = " ".join(notes)
    range_match = re.search(
        r"(?<!\d)(\d{1,3})\s*to\s*(\d{1,3})(?!\d)",
        note_text,
        re.IGNORECASE,
    )
    if range_match:
        lower, upper = range_match.groups()
        return f"{lower}–{upper}岁" if is_chinese else f"ages {lower}–{upper}"
    upper_match = re.search(
        r"(?<!\d)(\d{1,3})\s*or\s*older(?![a-z])",
        note_text,
        re.IGNORECASE,
    )
    if upper_match:
        age = upper_match.group(1)
        return f"{age}岁及以上" if is_chinese else f"age {age} or older"
    return None


def _localized_scope_note(note: str, *, is_chinese: bool) -> str:
    if not is_chinese:
        return note
    localized = re.sub(
        r"(?<!\d)(\d{1,3})\s*or\s*older(?![a-z])",
        lambda match: f"{match.group(1)}岁及以上",
        note,
        flags=re.IGNORECASE,
    )
    localized = re.sub(
        r"(?<!\d)(\d{1,3})\s*to\s*(\d{1,3})(?!\d)",
        lambda match: f"{match.group(1)}–{match.group(2)}岁",
        localized,
        flags=re.IGNORECASE,
    )
    return localized


def _diagnosis_families(labels: Sequence[str]) -> list[str]:
    joined = " ".join(_plain_diagnosis_name(label).upper() for label in labels)
    families: list[str] = []
    rules = (
        (("SEPTICEMIA", "CORONAVIRUS", "COVID", "PNEUMONIA"), "感染性疾病"),
        (("ALCOHOL",), "酒精相关疾病"),
        (("HEART", "CARDIAC", "CORONARY", "MYOCARDIAL"), "心血管疾病"),
        (("DIABETES",), "代谢性疾病"),
        (("OSTEO", "SPONDYLO", "ARTHR"), "肌肉骨骼疾病"),
    )
    for terms, family in rules:
        if any(term in joined for term in terms):
            families.append(family)
    return families[:4]


def _join_ranked_findings(items: Sequence[tuple[str, str]]) -> str:
    rendered = [f"{label}（{value}条）" for label, value in items]
    if len(rendered) == 1:
        return f"{rendered[0]}最多"
    if len(rendered) == 2:
        return f"{rendered[0]}最多，其次是{rendered[1]}"
    return f"{rendered[0]}最多，其次是{rendered[1]}和{rendered[2]}"


def _diagnosis_client_answer(
    question: str,
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]] | None:
    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    rows, used_ids = _diagnosis_ranking_rows(question, prepared)
    if not rows or not used_ids:
        return None

    localized = [
        (_localized_diagnosis_name(label, is_chinese=is_chinese), value)
        for label, value in rows
    ]
    if not is_chinese:
        top = localized[:3]
        findings = ", followed by ".join(
            f"{label} ({value} inpatient discharge records)" for label, value in top
        )
        answer = (
            "Conclusion: In the filtered aggregate cohort, the most frequent "
            f"principal diagnoses are {findings}.\n\n"
            "Statistical boundary: this describes the composition of inpatient "
            "discharge records and is not an individual's disease probability or diagnosis."
        )
        notes = _evidence_scope_notes(prepared)
        if notes:
            answer += "\n\nScope notes: " + "; ".join(notes[:2])
        return answer, used_ids

    notes = _evidence_scope_notes(prepared)
    group = _age_group_label(notes, is_chinese=True)
    exact_age = re.search(r"(?<!\d)(\d{1,3})\s*岁", question)
    gender = "男性" if "男性" in question else "女性" if "女性" in question else ""
    if group and exact_age:
        cohort_intro = (
            f"以{group}{gender}住院出院记录作为{exact_age.group(1)}岁{gender}所在年龄组的近似"
        )
    elif group:
        cohort_intro = f"在{group}{gender}住院出院记录中"
    else:
        cohort_intro = "在当前筛选的住院出院记录中"

    answer = (
        f"结论：{cohort_intro}，该组住院主诊断记录中，"
        f"{_join_ranked_findings(localized[:3])}。"
    )
    remaining = localized[3:5]
    families = _diagnosis_families([label for label, _ in rows[:5]])
    insights: list[str] = []
    ranking_analysis, _ = _ranking_analysis_for_dimension(prepared, "diagnosis")
    if ranking_analysis is not None:
        runner_up_gap = _fallback_number(ranking_analysis.runner_up_gap)
        if runner_up_gap is not None:
            insights.append(f"首位主诊断比第二位多{runner_up_gap}条记录")
    if remaining:
        insights.append(
            "前列主诊断还包括"
            + "和".join(f"{label}（{value}条）" for label, value in remaining)
        )
    if families:
        insights.append(
            "从前列主诊断构成看，"
            + "、".join(families)
            + "是该组住院运营需要重点关注的类别"
        )
    if insights:
        answer += "\n\n关键发现：" + "；".join(insights) + "。"

    boundary_group = f"{group}{gender}" if group else "当前筛选群体"
    exact_label = f"{exact_age.group(1)}岁个人" if exact_age else "个人"
    answer += (
        f"\n\n统计边界：这是{boundary_group}住院出院记录的组级近似，"
        f"不等同于{exact_label}的患病概率或医学诊断。"
    )
    if exact_age:
        answer += f"当前数据无法提供精确到{exact_age.group(1)}岁的单岁统计。"
        published_group = re.search(
            r"(?<!\d)(\d{1,3})\s*to\s*(\d{1,3})(?!\d)",
            " ".join(notes),
            re.IGNORECASE,
        )
        if published_group:
            answer += (
                f"发布年龄组：{published_group.group(1)} to {published_group.group(2)}。"
            )
    return answer, used_ids


def _hospital_client_answer(
    question: str,
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]] | None:
    analysis, used_ids = _ranking_analysis_for_dimension(prepared, "hospital")
    if analysis is None or not used_ids:
        return None

    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    notes = _evidence_scope_notes(prepared)
    group = _age_group_label(notes, is_chinese=is_chinese)
    top = [
        (item.label, _fallback_number(item.value) or str(item.value))
        for item in analysis.items[:3]
    ]

    if not is_chinese:
        cohort = f"for patients {group}" if group else "in the selected cohort"
        findings = ", followed by ".join(
            f"{label} ({value} {analysis.unit})" for label, value in top
        )
        return (
            f"Conclusion: {cohort}, the highest {analysis.measure} ranking is "
            f"{findings}.\n\n"
            "Statistical boundary: this is a hospital-level aggregate comparison, "
            "not a patient-level conclusion, causal explanation, or quality-of-care ranking."
        ), used_ids

    cohort = f"{group}人群" if group else "当前筛选人群"
    first_label, first_value = top[0]
    comparative = "最多" if analysis.measure == "case_count" else "最高"
    answer = (
        f"结论：在{cohort}的住院出院记录中，按医院汇总，"
        f"{first_label}的{analysis.measure_label}{comparative}，"
        f"为{first_value}{analysis.unit}。"
    )
    if len(top) > 1:
        followers = "，".join(
            f"{label}（{value}{analysis.unit}）" for label, value in top[1:]
        )
        answer += f"\n\n关键发现：其次依次为{followers}。"
        gap = _fallback_number(analysis.runner_up_gap)
        if gap is not None:
            gap_word = "多" if analysis.measure == "case_count" else "高"
            answer += (
                f"第一名的{analysis.measure_label}比第二名{gap_word}"
                f"{gap}{analysis.unit}。"
            )
    if analysis.measure == "case_count":
        answer += (
            "\n\n统计边界：这里的“最多”按医院汇总的住院出院记录数判断，"
            "不等同于独立患者人数、医院整体接诊能力或医疗质量排名。"
        )
    else:
        answer += (
            "\n\n统计边界：这是医院层面的聚合指标比较，不代表患者个体情况，"
            "也不能据此推断原因或评价医疗质量。"
        )
    return answer, used_ids


def _is_client_ready_answer(
    answer: str,
    question: str,
    prepared: Sequence[Mapping[str, Any]],
) -> bool:
    lowered = answer.casefold()
    if any(marker in lowered for marker in _INTERNAL_PROCESS_MARKERS):
        return False
    if not any("\u4e00" <= character <= "\u9fff" for character in question):
        return True
    cross_analysis, _ = _cross_cube_analysis(prepared)
    if cross_analysis is not None:
        if "结论" not in answer or "统计边界" not in answer:
            return False
        for dimension, value in cross_analysis.items[0].dimension_values:
            localized = _localized_cross_dimension_value(
                dimension,
                value,
                is_chinese=True,
            )
            if localized not in answer:
                return False
        return "住院出院记录" in answer
    hospital_analysis, _ = _ranking_analysis_for_dimension(prepared, "hospital")
    if hospital_analysis is not None:
        top_label = hospital_analysis.items[0].label
        if "结论" not in answer or top_label not in answer:
            return False
        notes = _evidence_scope_notes(prepared)
        group = _age_group_label(notes, is_chinese=True)
        if group and group not in answer:
            return False
        if "住院出院记录" not in answer:
            return False

    diagnosis_rows, _ = _diagnosis_ranking_rows(question, prepared)
    if not diagnosis_rows:
        return True
    top_label = _localized_diagnosis_name(diagnosis_rows[0][0], is_chinese=True)
    plain_top_label = _plain_diagnosis_name(diagnosis_rows[0][0])
    if top_label == plain_top_label and re.fullmatch(r"[A-Z]{1,5}\d{0,4}", top_label):
        # Synthetic or unpublished codes have no customer-facing localization
        # contract. Preserve a grounded model answer instead of inventing one.
        return True
    if "结论" not in answer:
        return False
    if top_label not in answer:
        return False
    notes = _evidence_scope_notes(prepared)
    group = _age_group_label(notes, is_chinese=True)
    if group and (group not in answer or "个人" not in answer):
        return False
    return True


def _deterministic_fallback_result(
    question: str,
    prepared: Sequence[Mapping[str, Any]],
    provenance: dict[str, str] | None,
) -> AnswerResult:
    cross_cube_answer = _cross_cube_client_answer(question, prepared)
    if cross_cube_answer is not None:
        answer, used_ids = cross_cube_answer
        return AnswerResult(
            status=ANSWER_STATUS_OK,
            answer_text=answer,
            used_evidence_ids=tuple(dict.fromkeys(used_ids)),
            provenance=dict(provenance) if provenance is not None else None,
        )

    diagnosis_answer = _diagnosis_client_answer(question, prepared)
    if diagnosis_answer is not None:
        answer, used_ids = diagnosis_answer
        return AnswerResult(
            status=ANSWER_STATUS_OK,
            answer_text=answer,
            used_evidence_ids=tuple(dict.fromkeys(used_ids)),
            provenance=dict(provenance) if provenance is not None else None,
        )

    hospital_answer = _hospital_client_answer(question, prepared)
    if hospital_answer is not None:
        answer, used_ids = hospital_answer
        return AnswerResult(
            status=ANSWER_STATUS_OK,
            answer_text=answer,
            used_evidence_ids=tuple(dict.fromkeys(used_ids)),
            provenance=dict(provenance) if provenance is not None else None,
        )

    lines, used_ids = _fallback_text_parts(prepared)
    if not lines or not used_ids:
        return _insufficient_result(provenance)

    notes = _evidence_scope_notes(prepared)

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

    is_chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    display_notes = [
        _localized_scope_note(note, is_chinese=is_chinese) for note in notes
    ]
    missing = [note for note in display_notes if note not in answer]
    if not missing:
        return answer
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
        if not _is_client_ready_answer(answer, normalized_question, prepared):
            return _deterministic_fallback_result(
                normalized_question,
                prepared,
                provenance,
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
