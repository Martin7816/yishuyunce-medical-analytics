"""Adapt validated query results into the existing Safe Evidence format.

This adapter deliberately delegates sanitization and deterministic fact
derivation to ``ai_evidence`` and chart selection to ``ai_chart``.  It only
maps semantic query rows into the existing snapshot-shaped input; it does not
create a second evidence or chart contract.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from shared.query_result_contract import (
    QueryResultContract,
    QueryResultContractError,
    validate_query_result,
)

from .ai_chart import build_chart_from_evidence
from .ai_evidence import build_safe_evidence
from .dimension_label_catalog import DimensionLabelResolver
from .diagnosis_label_catalog import DiagnosisLabelResolver
from .hospital_label_catalog import HospitalLabelResolver
from .query_intent import query_scope_notes


SUPPORTED_EVIDENCE_TYPES = frozenset(
    {"ranking", "comparison", "distribution", "relationship"}
)
_CHART_TYPES = {
    "ranking": "bar",
    "comparison": "grouped_bar",
    "distribution": "pie",
    "relationship": "scatter",
}
_MEASURE_LABELS = {
    "case_count": "Case count",
    "avg_los": "Average length of stay",
    "avg_charges": "Average charges",
    "avg_costs": "Average costs",
    "emergency_rate": "Emergency rate",
    "surgical_rate": "Surgical rate",
    "severe_rate": "Severe rate",
}
_DIMENSION_LABELS = {
    "hospital": "Hospital",
    "diagnosis": "Diagnosis",
    "age_group": "Age group",
    "gender": "Gender",
    "severity": "Severity",
    "payment": "Payment",
    "admission_type": "Admission type",
}


class QueryEvidenceAdapterError(ValueError):
    """Raised when a query result cannot be safely projected to evidence."""


def _number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal) and value.is_finite():
        converted = float(value)
        if math.isfinite(converted):
            return converted
    return None


def _dimension_label(result: QueryResultContract) -> str:
    if not result.dimensions:
        return "Aggregate"
    return " / ".join(
        _DIMENSION_LABELS.get(dimension, dimension)
        for dimension in result.dimensions
    )


def _display_dimension_value(
    dimension: str,
    value: object,
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver],
    data_version: str,
) -> str:
    code = str(value)
    resolver = label_resolvers.get(dimension)
    if resolver is None:
        return code
    try:
        label = resolver.resolve(code, data_version)
    except Exception:
        # A label source is optional display metadata; the code is the safe
        # canonical fallback if it cannot be resolved.
        label = None
    if not isinstance(label, str):
        return f"医院 {code}" if dimension == "hospital" and code.isdigit() else code
    label = label.strip()
    if (
        not label
        or label == code
        or len(label) > 255
        or any(ord(character) < 32 for character in label)
    ):
        return f"医院 {code}" if dimension == "hospital" and code.isdigit() else code
    if dimension == "hospital":
        return f"{label}（机构编码：{code}）"
    return f"{code} — {label}"


def _row_label(
    row: Mapping[str, Any],
    dimensions: tuple[str, ...],
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver] | None = None,
    data_version: str = "",
) -> str:
    if not dimensions:
        return "Aggregate"
    return " / ".join(
        _display_dimension_value(
            dimension,
            row[dimension],
            label_resolvers=label_resolvers or {},
            data_version=data_version,
        )
        for dimension in dimensions
    )


def _measure_label(measure: str) -> str:
    return _MEASURE_LABELS.get(measure, measure)


def _ranking_measure(result: QueryResultContract) -> str:
    if "case_count" in result.measures:
        return "case_count"
    return result.measures[0]


def _metrics(result: QueryResultContract) -> list[dict[str, Any]]:
    """Expose metrics only when one result row has no grouping ambiguity."""

    if result.dimensions or len(result.rows) != 1:
        return []
    row = result.rows[0]
    metrics: list[dict[str, Any]] = []
    for measure in result.measures:
        value = _number(row.get(measure))
        if value is None:
            continue
        metrics.append(
            {
                "key": measure,
                "label": _measure_label(measure),
                "value": value,
            }
        )
    return metrics


def _ranking_section(
    result: QueryResultContract,
    title: str,
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver],
) -> dict[str, Any]:
    measure = _ranking_measure(result)
    items: list[dict[str, Any]] = []
    for row in result.rows:
        value = _number(row.get(measure))
        if value is None:
            continue
        items.append(
            {
                "name": _row_label(
                    row,
                    result.dimensions,
                    label_resolvers=label_resolvers,
                    data_version=result.data_version,
                ),
                "value": value,
            }
        )
    items.sort(key=lambda item: float(item["value"]), reverse=True)
    return {
        "key": f"{result.dimensions[0] if result.dimensions else 'aggregate'}_ranking",
        "title": title,
        "type": "bar",
        "items": items,
        "visual": {
            "x_label": _dimension_label(result),
            "y_label": _measure_label(measure),
            "unit": _measure_label(measure),
        },
    }


def _comparison_section(
    result: QueryResultContract,
    title: str,
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in result.rows:
        series: list[dict[str, Any]] = []
        for measure in result.measures:
            value = _number(row.get(measure))
            if value is None:
                continue
            series.append(
                {
                    "key": measure,
                    "label": _measure_label(measure),
                    "value": value,
                }
            )
        items.append(
            {
                "category": _row_label(
                    row,
                    result.dimensions,
                    label_resolvers=label_resolvers,
                    data_version=result.data_version,
                ),
                "series": series,
            }
        )
    return {
        "key": f"{result.dimensions[0] if result.dimensions else 'aggregate'}_comparison",
        "title": title,
        "type": "grouped_bar",
        "items": items,
        "visual": {
            "x_label": _dimension_label(result),
            "y_label": "Selected measures",
        },
    }


def _distribution_section(
    result: QueryResultContract,
    title: str,
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver],
) -> dict[str, Any]:
    measure = _ranking_measure(result)
    items: list[dict[str, Any]] = []
    for row in result.rows:
        value = _number(row.get(measure))
        if value is None:
            continue
        items.append(
            {
                "name": _row_label(
                    row,
                    result.dimensions,
                    label_resolvers=label_resolvers,
                    data_version=result.data_version,
                ),
                "value": value,
            }
        )
    return {
        "key": f"{result.dimensions[0] if result.dimensions else 'aggregate'}_distribution",
        "title": title,
        "type": "pie",
        "items": items,
        "visual": {
            "x_label": _dimension_label(result),
            "y_label": _measure_label(measure),
            "unit": _measure_label(measure),
        },
    }


def _relationship_section(
    result: QueryResultContract,
    title: str,
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver],
) -> dict[str, Any]:
    measures = result.measures[:2]
    items: list[dict[str, Any]] = []
    if len(measures) == 2:
        for row in result.rows:
            x = _number(row.get(measures[0]))
            y = _number(row.get(measures[1]))
            if x is None or y is None:
                continue
            item: dict[str, Any] = {
                "name": _row_label(
                    row,
                    result.dimensions,
                    label_resolvers=label_resolvers,
                    data_version=result.data_version,
                ),
                "x": x,
                "y": y,
            }
            if result.dimensions:
                item["group"] = str(row[result.dimensions[0]])
            if "case_count" in result.measures and "case_count" not in measures:
                size = _number(row.get("case_count"))
                if size is not None:
                    item["size"] = size
            items.append(item)
    return {
        "key": f"{result.dimensions[0] if result.dimensions else 'aggregate'}_relationship",
        "title": title,
        "type": "scatter",
        "items": items,
        "visual": {
            "x_label": _measure_label(measures[0]) if measures else "",
            "y_label": _measure_label(measures[1]) if len(measures) == 2 else "",
        },
    }


def _section(
    result: QueryResultContract,
    section_type: str,
    title: str,
    *,
    label_resolvers: Mapping[str, DimensionLabelResolver],
) -> dict[str, Any]:
    if section_type == "ranking":
        return _ranking_section(
            result,
            title,
            label_resolvers=label_resolvers,
        )
    if section_type == "comparison":
        return _comparison_section(
            result,
            title,
            label_resolvers=label_resolvers,
        )
    if section_type == "distribution":
        return _distribution_section(
            result,
            title,
            label_resolvers=label_resolvers,
        )
    return _relationship_section(
        result,
        title,
        label_resolvers=label_resolvers,
    )


class QueryEvidenceAdapter:
    """Project one QueryResult v1 into the existing Safe Evidence pipeline."""

    def __init__(
        self,
        tool: str = "query_analytics",
        *,
        diagnosis_label_resolver: DiagnosisLabelResolver | None = None,
        hospital_label_resolver: HospitalLabelResolver | None = None,
    ) -> None:
        self.tool = tool
        self.label_resolvers: dict[str, DimensionLabelResolver] = {}
        if diagnosis_label_resolver is not None:
            self.label_resolvers["diagnosis"] = diagnosis_label_resolver
        if hospital_label_resolver is not None:
            self.label_resolvers["hospital"] = hospital_label_resolver

    def adapt(
        self,
        result: QueryResultContract | Mapping[str, Any],
        section_type: str = "ranking",
        *,
        title: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        if section_type not in SUPPORTED_EVIDENCE_TYPES:
            raise QueryEvidenceAdapterError(
                f"unsupported query evidence type: {section_type}"
            )

        try:
            if isinstance(result, QueryResultContract):
                # Re-validate the serialized value so mutable nested mappings
                # cannot bypass the shared result contract.
                validated = validate_query_result(result.to_document())
            else:
                validated = validate_query_result(result)
        except QueryResultContractError as error:
            raise QueryEvidenceAdapterError(str(error)) from error

        section_title = title or (
            f"{section_type.title()} by {_dimension_label(validated)}"
        )
        section = _section(
            validated,
            section_type,
            section_title,
            label_resolvers=self.label_resolvers,
        )
        snapshot = {
            "title": section_title,
            "description": (
                "Values are projected from the validated aggregate query result."
            ),
            "data_version": validated.data_version,
            "generated_at": validated.metadata["generated_at"],
            "metrics": _metrics(validated),
            "sections": [section],
        }

        try:
            evidence = build_safe_evidence(self.tool, snapshot)
        except (TypeError, ValueError) as error:
            raise QueryEvidenceAdapterError(str(error)) from error

        # Keep the existing ``derived_facts`` contract as the source of truth;
        # ``facts`` is a compatibility alias for query consumers.
        evidence["facts"] = list(evidence.get("derived_facts", []))
        evidence["provenance"] = dict(validated.provenance)
        evidence["query_id"] = validated.query_id
        evidence["query_plan"] = validated.query_plan
        scope_notes = query_scope_notes(question)
        if scope_notes:
            evidence["query_scope_notes"] = list(scope_notes)
            limitations = evidence.get("limitations")
            if not isinstance(limitations, list):
                limitations = []
            evidence["limitations"] = list(dict.fromkeys([*limitations, *scope_notes]))

        chart_question = question or f"{section_type} {_dimension_label(validated)}"
        chart = build_chart_from_evidence(chart_question, [evidence])
        if chart is not None and chart.get("type") != _CHART_TYPES[section_type]:
            chart = None
        if chart is not None:
            chart = dict(chart)
            chart["provenance"] = dict(validated.provenance)
        evidence["chart"] = chart
        return evidence

    def build(
        self,
        result: QueryResultContract | Mapping[str, Any],
        section_type: str = "ranking",
        *,
        title: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        return self.adapt(
            result,
            section_type,
            title=title,
            question=question,
        )


def adapt_query_result(
    result: QueryResultContract | Mapping[str, Any],
    section_type: str = "ranking",
    *,
    title: str | None = None,
    question: str | None = None,
    diagnosis_label_resolver: DiagnosisLabelResolver | None = None,
    hospital_label_resolver: HospitalLabelResolver | None = None,
) -> dict[str, Any]:
    """Adapt a QueryResult through the existing Safe Evidence and chart code."""

    return QueryEvidenceAdapter(
        diagnosis_label_resolver=diagnosis_label_resolver,
        hospital_label_resolver=hospital_label_resolver,
    ).adapt(
        result,
        section_type,
        title=title,
        question=question,
    )


build_query_evidence = adapt_query_result


__all__ = [
    "QueryEvidenceAdapter",
    "QueryEvidenceAdapterError",
    "SUPPORTED_EVIDENCE_TYPES",
    "adapt_query_result",
    "build_query_evidence",
]
