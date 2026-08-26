"""Deterministic business analysis of validated aggregate rankings.

The module consumes Safe Evidence only. It never reads a database, calls a
model, estimates missing values, or treats a returned Top-K subset as a full
distribution. Its small interface hides measure semantics, numeric validation,
ordering, and runner-up comparison from answer generators.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


_MEASURE_PRESENTATION = {
    "case_count": ("病例量", "条"),
    "avg_los": ("平均住院时长", "天"),
    "avg_charges": ("平均收费", "美元"),
    "avg_costs": ("平均成本", "美元"),
    "emergency_rate": ("急诊率", "%"),
    "surgical_rate": ("手术相关率", "%"),
    "severe_rate": ("重症率", "%"),
}


@dataclass(frozen=True, slots=True)
class RankedEvidenceItem:
    label: str
    value: int | float


@dataclass(frozen=True, slots=True)
class RankingEvidenceAnalysis:
    dimension: str
    measure: str
    measure_label: str
    unit: str
    items: tuple[RankedEvidenceItem, ...]
    runner_up_gap: int | float | None
    returned_item_count: int


@dataclass(frozen=True, slots=True)
class CrossCubeRankedItem:
    dimension_values: tuple[tuple[str, str], ...]
    value: int | float


@dataclass(frozen=True, slots=True)
class CrossCubeRankingAnalysis:
    dimensions: tuple[str, ...]
    measure: str
    measure_label: str
    unit: str
    items: tuple[CrossCubeRankedItem, ...]
    returned_item_count: int


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def _measure(evidence: Mapping[str, Any]) -> str:
    query_plan = evidence.get("query_plan")
    if isinstance(query_plan, Mapping):
        measures = query_plan.get("measures")
        if isinstance(measures, Sequence) and not isinstance(measures, (str, bytes)):
            for measure in measures:
                if isinstance(measure, str) and measure in _MEASURE_PRESENTATION:
                    return measure
    return "case_count"


def analyze_evidence_ranking(
    evidence: Mapping[str, Any],
    dimension: str,
) -> RankingEvidenceAnalysis | None:
    """Return bounded ranking insights for one semantic dimension."""

    if not isinstance(evidence, Mapping) or not isinstance(dimension, str):
        return None
    section_key = f"{dimension}_ranking"
    sections = evidence.get("sections")
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return None

    for section in sections:
        if not isinstance(section, Mapping) or section.get("key") != section_key:
            continue
        raw_items = section.get("items")
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            return None

        items: list[RankedEvidenceItem] = []
        for raw_item in raw_items[:10]:
            if not isinstance(raw_item, Mapping):
                continue
            label = raw_item.get("name", raw_item.get("category"))
            value = _number(raw_item.get("value"))
            if not isinstance(label, str) or not label.strip() or value is None:
                continue
            items.append(RankedEvidenceItem(label.strip(), value))
        if not items:
            return None
        items.sort(key=lambda item: float(item.value), reverse=True)

        measure = _measure(evidence)
        measure_label, unit = _MEASURE_PRESENTATION[measure]
        runner_up_gap: int | float | None = None
        if len(items) >= 2:
            gap = float(items[0].value) - float(items[1].value)
            runner_up_gap = int(gap) if gap.is_integer() else round(gap, 6)
        return RankingEvidenceAnalysis(
            dimension=dimension,
            measure=measure,
            measure_label=measure_label,
            unit=unit,
            items=tuple(items),
            runner_up_gap=runner_up_gap,
            returned_item_count=len(items),
        )
    return None


def analyze_cross_cube_ranking(
    evidence: Mapping[str, Any],
) -> CrossCubeRankingAnalysis | None:
    """Return ranked combinations for one reviewed multi-dimension cube.

    The evidence adapter joins dimension display values with ``" / "``.  The
    query plan supplies the canonical dimension order, so this function can
    recover a structured, bounded view without exposing physical fields.
    """

    if not isinstance(evidence, Mapping):
        return None
    query_plan = evidence.get("query_plan")
    if not isinstance(query_plan, Mapping):
        return None
    raw_dimensions = query_plan.get("dimensions")
    if not isinstance(raw_dimensions, Sequence) or isinstance(
        raw_dimensions, (str, bytes)
    ):
        return None
    dimensions = tuple(
        dimension for dimension in raw_dimensions if isinstance(dimension, str)
    )
    if len(dimensions) < 2 or len(dimensions) != len(raw_dimensions):
        return None

    sections = evidence.get("sections")
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return None
    expected_key = f"{dimensions[0]}_ranking"
    for section in sections:
        if not isinstance(section, Mapping) or section.get("key") != expected_key:
            continue
        raw_items = section.get("items")
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            return None
        items: list[CrossCubeRankedItem] = []
        for raw_item in raw_items[:10]:
            if not isinstance(raw_item, Mapping):
                continue
            label = raw_item.get("name")
            value = _number(raw_item.get("value"))
            if not isinstance(label, str) or value is None:
                continue
            labels = tuple(part.strip() for part in label.split(" / "))
            if len(labels) != len(dimensions) or any(not part for part in labels):
                continue
            items.append(
                CrossCubeRankedItem(
                    dimension_values=tuple(zip(dimensions, labels)),
                    value=value,
                )
            )
        if not items:
            return None
        items.sort(key=lambda item: float(item.value), reverse=True)
        measure = _measure(evidence)
        measure_label, unit = _MEASURE_PRESENTATION[measure]
        return CrossCubeRankingAnalysis(
            dimensions=dimensions,
            measure=measure,
            measure_label=measure_label,
            unit=unit,
            items=tuple(items),
            returned_item_count=len(items),
        )
    return None


__all__ = [
    "CrossCubeRankedItem",
    "CrossCubeRankingAnalysis",
    "RankedEvidenceItem",
    "RankingEvidenceAnalysis",
    "analyze_cross_cube_ranking",
    "analyze_evidence_ranking",
]
