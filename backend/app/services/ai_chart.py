"""Deterministic chart selection from already validated AI evidence."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


SIMPLE_CHART_TYPES = frozenset({"bar", "pie", "table", "status"})
COMPLEX_CHART_TYPES = frozenset({"grouped_bar", "scatter", "heatmap"})
CHART_TYPES = SIMPLE_CHART_TYPES | COMPLEX_CHART_TYPES

_MAX_METRIC_ITEMS = 8
_MAX_SIMPLE_ITEMS = 20

_TOOL_DEFAULT_KEYS = {
    "get_dashboard_overview": ("hospital_top10", "disease_top10", "severity"),
    "get_hospital_overview": ("ranking", "facility_metric_comparison", "facility_relation"),
    "get_disease_overview": ("top10", "diseases"),
    "get_cohort_summary": ("age", "gender", "severity", "diseases"),
    "get_cost_overview": ("quantiles", "severity", "cost_los_relation"),
    "get_risk_overview": ("age_severity_matrix", "severity", "mortality", "diseases"),
    "get_payment_overview": ("payment", "charges", "age", "diseases"),
    "get_model_metrics": ("confusion",),
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _lower(value: Any) -> str:
    return _text(value).lower()


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def _contains(text: str, terms: Sequence[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _question_profile(question: str) -> dict[str, bool]:
    text = _lower(question)
    return {
        "hospital": _contains(text, ("医院", "医疗机构", "机构", "hospital", "facility")),
        "disease": _contains(text, ("疾病", "病种", "诊断", "disease", "diagnosis")),
        "cost": _contains(text, ("收费", "费用", "成本", "花费", "cost", "charge", "expense")),
        "risk": _contains(text, ("风险", "严重程度", "重症", "死亡", "risk", "severity", "mortality")),
        "payment": _contains(text, ("支付", "付款", "医保", "自费", "payment", "payer")),
        "age": _contains(text, ("年龄", "age")),
        "gender": _contains(text, ("性别", "gender")),
        "admission": _contains(text, ("入院", "admission")),
        "ranking": _contains(text, ("最高", "最多", "排名", "排行", "top", "highest", "most", "ranking")),
        "comparison": _contains(text, ("对比", "比较", "对照", "差异", "compare", "versus", " vs ")),
        "relationship": _contains(text, ("关系", "相关", "关联", "relationship", "correlation")),
        "distribution": _contains(text, ("分布", "分位", "distribution", "quantile")),
        "structure": _contains(text, ("结构", "构成", "人群", "structure")),
        "model": _contains(text, ("模型", "准确率", "精确率", "召回", "auc", "f1", "model", "accuracy")),
    }


def _metadata(section: Mapping[str, Any]) -> str:
    visual = section.get("visual")
    visual_question = visual.get("question") if isinstance(visual, Mapping) else ""
    return " ".join(
        value
        for value in (
            _lower(section.get("key")),
            _lower(section.get("title")),
            _lower(visual_question),
        )
        if value
    )


def _section_score(
    question: str,
    profile: Mapping[str, bool],
    source: Mapping[str, Any],
    section: Mapping[str, Any],
) -> int:
    key = _lower(section.get("key"))
    section_type = _lower(section.get("type"))
    metadata = _metadata(section)
    score = 0

    if profile["hospital"]:
        if profile["ranking"] and key in {"ranking", "hospital_top10", "top10"}:
            score += 240
        if profile["relationship"] and key == "facility_relation":
            score += 240
        if profile["comparison"] and key == "facility_metric_comparison":
            score += 240
        if "hospital" in key or "facility" in key or "医疗机构" in metadata:
            score += 35

    if profile["disease"]:
        if key in {"disease_top10", "diagnosis_top10", "top10", "diseases"}:
            score += 220 if profile["ranking"] else 135
        if "disease" in key or "diagnosis" in key or "疾病" in metadata:
            score += 35

    if profile["cost"]:
        if profile["distribution"] and key in {"quantiles", "cost_distribution"}:
            score += 240
        if profile["comparison"] and key == "severity":
            score += 205
        if profile["relationship"] and key in {"cost_los_relation", "facility_relation"}:
            score += 230
        if "cost" in key or "charge" in key or "收费" in metadata or "费用" in metadata:
            score += 35

    if profile["risk"]:
        if profile["structure"] and key == "age_severity_matrix":
            score += 245
        if key in {"severity", "mortality", "disposition"}:
            score += 185
        if section_type == "heatmap":
            score += 65
        if "risk" in key or "severity" in key or "风险" in metadata or "严重" in metadata:
            score += 35

    if profile["payment"]:
        if key in {"payment", "charges"}:
            score += 220 if key == "payment" else 145
        if "payment" in key or "支付" in metadata:
            score += 35

    if profile["age"] and key == "age":
        score += 220
    if profile["gender"] and key == "gender":
        score += 220
    if profile["admission"] and key in {"admission", "admission_type"}:
        score += 220

    if profile["relationship"] and section_type == "scatter":
        score += 75
    if profile["comparison"] and section_type == "grouped_bar":
        score += 55
    if profile["distribution"] and section_type in {"bar", "pie"}:
        score += 20
    if profile["model"] and key == "confusion":
        score += 240

    if not any(profile.values()):
        default_keys = _TOOL_DEFAULT_KEYS.get(_text(source.get("tool")), ())
        if key in default_keys:
            score += 150 - default_keys.index(key) * 10

    # Give an explicitly named section a small deterministic advantage without
    # ever using answer text or generating values from the answer.
    question_words = set(re.findall(r"[a-z][a-z0-9_-]{2,}", _lower(question)))
    for word in question_words:
        if word in metadata:
            score += 8
    return score


def _copy_visual(visual: Any) -> dict[str, Any] | None:
    if not isinstance(visual, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in ("question", "x_label", "y_label", "unit"):
        value = _text(visual.get(key))
        if value:
            result[key] = value

    legend = visual.get("legend")
    if isinstance(legend, Sequence) and not isinstance(legend, (str, bytes)):
        safe_legend = []
        for item in legend[:32]:
            if not isinstance(item, Mapping):
                continue
            entry = {
                key: _text(item.get(key))
                for key in ("key", "label", "style")
                if _text(item.get(key))
            }
            if entry:
                safe_legend.append(entry)
        if safe_legend:
            result["legend"] = safe_legend

    summary = visual.get("summary")
    if isinstance(summary, Mapping):
        safe_summary: dict[str, Any] = {}
        for key in ("text", "source_section", "data_version", "generated_at", "boundary"):
            value = _text(summary.get(key))
            if value:
                safe_summary[key] = value
        if isinstance(summary.get("related_not_causal"), bool):
            safe_summary["related_not_causal"] = summary["related_not_causal"]
        if safe_summary:
            result["summary"] = safe_summary

    fallback = visual.get("fallback")
    if isinstance(fallback, Mapping):
        fallback_result = {"type": _text(fallback.get("type"))}
        columns = fallback.get("columns")
        if isinstance(columns, Sequence) and not isinstance(columns, (str, bytes)):
            fallback_result["columns"] = [
                value for value in (_text(item) for item in columns[:32]) if value
            ]
        if fallback_result.get("type") or fallback_result.get("columns"):
            result["fallback"] = fallback_result

    empty = visual.get("empty")
    if isinstance(empty, Mapping):
        empty_result = {
            key: _text(empty.get(key))
            for key in ("title", "text")
            if _text(empty.get(key))
        }
        if empty_result:
            result["empty"] = empty_result
    return result or None


def _simple_items(section_type: str, raw_items: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return None
    items: list[dict[str, Any]] = []
    for item in raw_items[:_MAX_SIMPLE_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        name = _text(item.get("name"))
        value = item.get("value") if section_type == "status" else _number(item.get("value"))
        if not name or value is None:
            continue
        items.append({"name": name, "value": value})
    return items or None


def _complex_items(section_type: str, raw_items: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return None
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        if section_type == "grouped_bar":
            category = _text(item.get("category"))
            series = item.get("series")
            if not category or not isinstance(series, Sequence) or isinstance(series, (str, bytes)):
                continue
            safe_series = []
            for point in series[:32]:
                if not isinstance(point, Mapping):
                    continue
                key = _text(point.get("key"))
                label = _text(point.get("label"))
                value = _number(point.get("value"))
                if key and label and value is not None:
                    safe_series.append({"key": key, "label": label, "value": value})
            if safe_series:
                items.append({"category": category, "series": safe_series})
        elif section_type == "scatter":
            name = _text(item.get("name"))
            x = _number(item.get("x"))
            y = _number(item.get("y"))
            if not name or x is None or y is None:
                continue
            safe_item: dict[str, Any] = {"name": name, "x": x, "y": y}
            group = _text(item.get("group"))
            if group:
                safe_item["group"] = group
            for key in ("size", "cost", "high_cost_rate"):
                value = _number(item.get(key))
                if value is not None:
                    safe_item[key] = value
            items.append(safe_item)
        else:
            x_label = _text(item.get("x_label"))
            y_label = _text(item.get("y_label"))
            value = _number(item.get("value"))
            if not x_label or not y_label or value is None:
                continue
            safe_item = {"x_label": x_label, "y_label": y_label, "value": value}
            unit = _text(item.get("unit"))
            if unit:
                safe_item["unit"] = unit
            for key in ("numerator", "denominator", "high_risk_rate"):
                number = _number(item.get(key))
                if number is not None:
                    safe_item[key] = number
            items.append(safe_item)
    return items or None


def _section_chart(source: Mapping[str, Any], section: Mapping[str, Any]) -> dict[str, Any] | None:
    section_type = _text(section.get("type"))
    key = _text(section.get("key"))
    title = _text(section.get("title"))
    data_version = _text(source.get("data_version"))
    if section_type not in CHART_TYPES or not key or not title or not data_version:
        return None

    if section_type in SIMPLE_CHART_TYPES:
        items = _simple_items(section_type, section.get("items"))
    else:
        items = _complex_items(section_type, section.get("items"))
    if not items:
        return None

    chart: dict[str, Any] = {
        "type": section_type,
        "title": title,
        "items": items,
        "source_section": key,
        "source_tool": _text(source.get("tool")),
        "data_version": data_version,
    }
    visual = _copy_visual(section.get("visual"))
    if visual:
        chart["visual"] = visual
    return chart


def _metrics_chart(source: Mapping[str, Any]) -> dict[str, Any] | None:
    data_version = _text(source.get("data_version"))
    title = _text(source.get("title"))
    if not data_version or not title:
        return None
    metrics = source.get("metrics")
    if not isinstance(metrics, Sequence) or isinstance(metrics, (str, bytes)):
        return None
    items = []
    source_metric_keys = []
    for metric in metrics[:_MAX_METRIC_ITEMS]:
        if not isinstance(metric, Mapping):
            continue
        label = _text(metric.get("label"))
        value = _number(metric.get("value"))
        key = _text(metric.get("key"))
        if not label or value is None:
            continue
        items.append({"name": label, "value": value})
        if key:
            source_metric_keys.append(key)
    if not items:
        return None
    return {
        "type": "bar",
        "title": f"{title}来源指标",
        "items": items,
        "source_tool": _text(source.get("tool")),
        "data_version": data_version,
        "source_metric_keys": source_metric_keys,
    }


def _source_score(source: Mapping[str, Any], profile: Mapping[str, bool]) -> int:
    tool = _text(source.get("tool"))
    score = 0
    if profile["hospital"] and tool == "get_hospital_overview":
        score += 80
    if profile["disease"] and tool == "get_disease_overview":
        score += 80
    if profile["cost"] and tool == "get_cost_overview":
        score += 80
    if profile["risk"] and tool == "get_risk_overview":
        score += 80
    if profile["payment"] and tool == "get_payment_overview":
        score += 80
    if profile["model"] and tool == "get_model_metrics":
        score += 80
    return score


def build_chart_from_evidence(
    question: str,
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Select one chart using only safe sections, then fall back to metrics.

    The answer text is intentionally not an input to chart construction. Every
    emitted value is copied from a validated section item or validated metric.
    """

    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        return None
    profile = _question_profile(question)
    candidates: list[tuple[int, int, int, dict[str, Any]]] = []
    for source_index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            continue
        sections = source.get("sections")
        if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
            continue
        for section_index, section in enumerate(sections):
            if not isinstance(section, Mapping):
                continue
            chart = _section_chart(source, section)
            if chart is None:
                continue
            score = _section_score(question, profile, source, section) + _source_score(source, profile)
            candidates.append((score, -source_index, -section_index, chart))

    if candidates:
        candidates.sort(reverse=True, key=lambda candidate: candidate[:3])
        return candidates[0][3]

    metric_candidates = [
        (_source_score(source, profile), -index, _metrics_chart(source))
        for index, source in enumerate(sources)
        if isinstance(source, Mapping)
    ]
    metric_candidates = [candidate for candidate in metric_candidates if candidate[2] is not None]
    if not metric_candidates:
        return None
    metric_candidates.sort(reverse=True, key=lambda candidate: (candidate[0], candidate[1]))
    return metric_candidates[0][2]
