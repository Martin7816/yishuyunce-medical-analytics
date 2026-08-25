"""Build the bounded evidence handed to the analysis model.

The analytics snapshot is already validated at the repository boundary.  This
module applies a second, AI-specific projection so that the model receives
only the fields that are useful for analysis.  It also computes small,
deterministic facts from the aggregate data.  It deliberately does not run
SQL, inspect patient records, calculate statistical significance, or infer
causality.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


ANSWERABILITY_STATUSES = frozenset(
    {"answerable", "partially_answerable", "unsupported", "unsafe"}
)

SAFE_BOUNDARY = (
    "当前证据来自已发布的住院出院记录群体汇总；不包含患者级明细，"
    "不用于因果、诊断或治疗判断。"
)

_MAX_TEXT_LENGTH = 512
_MAX_ITEMS = 500
_MAX_INSIGHTS = 32
_MAX_FACTS = 80
_NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")

_SIMPLE_SECTION_TYPES = frozenset({"bar", "pie", "table", "status"})
_COMPLEX_SECTION_TYPES = frozenset({"grouped_bar", "scatter", "heatmap", "correlation"})

_UNSAFE_TERMS = (
    "个人诊断",
    "患者诊断",
    "病人诊断",
    "治疗建议",
    "治疗方案",
    "应该接受什么治疗",
    "吃什么药",
    "开药",
    "患者明细",
    "病人明细",
    "个体预测",
    "个人预测",
    "患者预测",
    "预测张三",
    "张三",
    "身份证",
    "姓名",
    "select ",
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "sql",
)

# ``患者``/``病人`` alone is not a patient-level request: cohort questions
# commonly use those words (for example, "Medicare患者平均费用").  Keep the
# privacy boundary focused on individual records, identifiers, and explicit
# single-person wording instead of rejecting every cohort aggregate.
_PATIENT_LEVEL_QUESTION_PATTERN = re.compile(
    r"(?:"
    r"\b(?:a|an|one|single|specific|individual|particular)\s+patient(?:'s)?\b"
    r"|\bpatient(?:[- ]level|[- ]data|[- ]records?|[- ]details?|[_ ]id)\b"
    r"|\b(?:mrn|ssn)\b"
    r"|(?:\u67d0|\u5355\u4e2a|\u5355\u4e00|\u5177\u4f53|\u8fd9\u540d|\u8fd9\u4e2a|\u8be5)\s*(?:\u60a3\u8005|\u75c5\u4eba)"
    r"|(?:\u60a3\u8005|\u75c5\u4eba)\s*(?:\u672c\u4eba|\u7ea7|\u660e\u7ec6|\u8be6\u60c5|\u8d26\u5355|\u8d39\u7528\u660e\u7ec6|\u8bb0\u5f55|\u7f16\u53f7|\u8eab\u4efd|ID|id)"
    r"|(?:\u4e2a\u4eba|\u4e2a\u4f53)\s*(?:\u60a3\u8005|\u75c5\u4eba|\u8d39\u7528|\u8d26\u5355|\u8bb0\u5f55)"
    r")",
    re.IGNORECASE,
)

_TREND_TERMS = (
    "同比",
    "环比",
    "趋势",
    "增长",
    "下降",
    "上升",
    "今年",
    "去年",
    "上月",
    "本月",
    "历史变化",
    "时间变化",
)

_CAUSAL_TERMS = (
    "为什么",
    "原因",
    "导致",
    "因果",
    "归因",
    "是否因为",
    "正相关",
    "相关性",
)

_RANKING_TERMS = ("最高", "最多", "最少", "排名", "排行", "top", "第一", "前几")
_STRUCTURE_TERMS = ("结构", "分布", "构成", "占比", "比例", "集中")
_RELATION_TERMS = ("关系", "关联", "相关", "正相关", "负相关")
_FOCUS_TERMS = ("重点", "关注", "优先", "值得注意", "值得关注")

_SIMPLE_CONVERSATION_PHRASES = frozenset(
    {
        "你好",
        "您好",
        "你好呀",
        "您好呀",
        "你好啊",
        "您好啊",
        "hello",
        "hi",
        "hey",
        "谢谢",
        "多谢",
        "谢谢你",
        "谢谢你的帮助",
        "谢谢您的帮助",
        "再见",
        "拜拜",
        "你是谁",
        "你是谁呀",
        "你是谁呢",
        "你是什么",
        "你是什么助手",
        "你是什么系统",
        "你能做什么",
        "你可以分析什么",
        "怎么用你",
        "怎么使用你",
        "帮助",
        "help",
        "who are you",
        "what are you",
        "what can you do",
        "what do you do",
        "how can you help",
        "how do i use you",
        "how to use you",
        "what can i ask",
        "what can you analyze",
    }
)
_CONVERSATION_EDGE_PUNCTUATION = " \t\r\n.,!?！？。，、；;：:~～…"

_TOOL_TOPIC = {
    "get_dashboard_overview": "overall",
    "get_hospital_overview": "hospital",
    "get_disease_overview": "disease",
    "get_cohort_summary": "cohort",
    "get_cost_overview": "cost",
    "get_risk_overview": "risk",
    "get_payment_overview": "payment",
    "get_model_metrics": "model",
}


def _safe_text(value: Any, *, max_length: int = _MAX_TEXT_LENGTH) -> str | None:
    """Return plain text only; never copy markup or control characters."""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > max_length:
        return None
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        return None

    lowered = text.lower()
    if any(
        marker in lowered
        for marker in (
            "<script",
            "javascript:",
            "<iframe",
            "```",
            "</script",
            "select ",
            "insert ",
            "update ",
            "delete ",
            "drop ",
            "alter ",
            "union select",
        )
    ):
        return None
    return text


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def _required_text(value: Any, field: str) -> str:
    text = _safe_text(value)
    if text is None:
        raise ValueError(f"invalid evidence field: {field}")
    return text


def _rounded(value: int | float, digits: int = 6) -> int | float:
    rounded = round(float(value), digits)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _safe_metric(metric: Mapping[str, Any]) -> dict[str, Any]:
    key = _required_text(metric.get("key"), "metrics.key")
    label = _required_text(metric.get("label"), "metrics.label")
    value = _safe_number(metric.get("value"))
    if value is None:
        raise ValueError("invalid evidence field: metrics.value")

    result: dict[str, Any] = {"key": key, "label": label, "value": value}
    unit = _safe_text(metric.get("unit"), max_length=64)
    if unit is not None:
        result["unit"] = unit
    return result


def _safe_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("text", "source_metric_keys", "source_section", "data_version", "generated_at", "boundary"):
        value = summary.get(key)
        if key == "source_metric_keys":
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                result[key] = [
                    text
                    for text in (_safe_text(item, max_length=128) for item in value[:32])
                    if text is not None
                ]
            continue
        text = _safe_text(value)
        if text is not None:
            result[key] = text
    related_not_causal = summary.get("related_not_causal")
    if isinstance(related_not_causal, bool):
        result["related_not_causal"] = related_not_causal
    return result


def _safe_visual(visual: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("question", "x_label", "y_label", "unit"):
        text = _safe_text(visual.get(key), max_length=256)
        if text is not None:
            result[key] = text

    legend = visual.get("legend")
    if isinstance(legend, Sequence) and not isinstance(legend, (str, bytes)):
        safe_legend: list[dict[str, Any]] = []
        for item in legend[:32]:
            if not isinstance(item, Mapping):
                continue
            item_result: dict[str, Any] = {}
            for key in ("key", "label", "style"):
                text = _safe_text(item.get(key), max_length=128)
                if text is not None:
                    item_result[key] = text
            if item_result:
                safe_legend.append(item_result)
        if safe_legend:
            result["legend"] = safe_legend

    tooltip_fields = visual.get("tooltip_fields")
    if isinstance(tooltip_fields, Sequence) and not isinstance(tooltip_fields, (str, bytes)):
        result["tooltip_fields"] = [
            text
            for text in (_safe_text(item, max_length=128) for item in tooltip_fields[:32])
            if text is not None
        ]

    summary = visual.get("summary")
    if isinstance(summary, Mapping):
        safe_summary = _safe_summary(summary)
        if safe_summary:
            result["summary"] = safe_summary

    fallback = visual.get("fallback")
    if isinstance(fallback, Mapping):
        fallback_result: dict[str, Any] = {}
        for key in ("type", "columns"):
            value = fallback.get(key)
            if key == "columns" and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                fallback_result[key] = [
                    text
                    for text in (_safe_text(item, max_length=128) for item in value[:32])
                    if text is not None
                ]
            else:
                text = _safe_text(value, max_length=128)
                if text is not None:
                    fallback_result[key] = text
        if fallback_result:
            result["fallback"] = fallback_result

    empty = visual.get("empty")
    if isinstance(empty, Mapping):
        empty_result: dict[str, Any] = {}
        for key in ("title", "text"):
            text = _safe_text(empty.get(key), max_length=256)
            if text is not None:
                empty_result[key] = text
        if empty_result:
            result["empty"] = empty_result
    return result


def _safe_section_item(section_type: str, item: Mapping[str, Any]) -> dict[str, Any] | None:
    if section_type in _SIMPLE_SECTION_TYPES:
        name = _safe_text(item.get("name"), max_length=256)
        if name is None:
            return None
        value = item.get("value")
        if section_type == "status":
            safe_value = _safe_text(value, max_length=256)
        else:
            safe_value = _safe_number(value)
        if safe_value is None:
            return None
        return {"name": name, "value": safe_value}

    if section_type == "grouped_bar":
        category = _safe_text(item.get("category"), max_length=256)
        series = item.get("series")
        if category is None or not isinstance(series, Sequence) or isinstance(series, (str, bytes)):
            return None
        safe_series: list[dict[str, Any]] = []
        for point in series[:32]:
            if not isinstance(point, Mapping):
                continue
            key = _safe_text(point.get("key"), max_length=128)
            label = _safe_text(point.get("label"), max_length=256)
            value = _safe_number(point.get("value"))
            if key is None or label is None or value is None:
                continue
            safe_series.append({"key": key, "label": label, "value": value})
        return {"category": category, "series": safe_series}

    if section_type == "scatter":
        result: dict[str, Any] = {}
        for key in ("name", "group"):
            text = _safe_text(item.get(key), max_length=256)
            if text is not None:
                result[key] = text
        for key in ("x", "y", "size", "cost", "high_cost_rate"):
            value = _safe_number(item.get(key))
            if value is not None:
                result[key] = value
        if "name" not in result or "x" not in result or "y" not in result:
            return None
        return result

    if section_type == "heatmap":
        result = {}
        for key in ("x_label", "y_label", "unit"):
            text = _safe_text(item.get(key), max_length=256)
            if text is not None:
                result[key] = text
        for key in ("value", "numerator", "denominator", "high_risk_rate"):
            value = _safe_number(item.get(key))
            if value is not None:
                result[key] = value
        if "x_label" not in result or "y_label" not in result or "value" not in result:
            return None
        return result

    if section_type == "correlation":
        result = {}
        for key in ("x_key", "x_label", "y_key", "y_label", "method"):
            text = _safe_text(item.get(key), max_length=256)
            if text is not None:
                result[key] = text
        for key in ("coefficient", "sample_size"):
            value = _safe_number(item.get(key))
            if value is not None:
                result[key] = value
        required = ("x_key", "x_label", "y_key", "y_label", "coefficient")
        if any(key not in result for key in required):
            return None
        return result

    return None


def _safe_section(section: Mapping[str, Any]) -> dict[str, Any]:
    key = _required_text(section.get("key"), "sections.key")
    title = _required_text(section.get("title"), "sections.title")
    section_type = _required_text(section.get("type"), "sections.type")
    if section_type not in _SIMPLE_SECTION_TYPES | _COMPLEX_SECTION_TYPES:
        raise ValueError(f"unsupported evidence section type: {section_type}")

    items = section.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ValueError("invalid evidence field: sections.items")
    safe_items = [
        safe_item
        for item in items[:_MAX_ITEMS]
        if isinstance(item, Mapping)
        for safe_item in [_safe_section_item(section_type, item)]
        if safe_item is not None
    ]

    result: dict[str, Any] = {
        "key": key,
        "title": title,
        "type": section_type,
        "items": safe_items,
    }
    visual = section.get("visual")
    if isinstance(visual, Mapping):
        safe_visual = _safe_visual(visual)
        if safe_visual:
            result["visual"] = safe_visual
    return result


def _safe_insight(insight: Mapping[str, Any]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for key in ("key", "title", "summary", "level", "source_section", "data_version", "generated_at", "boundary"):
        text = _safe_text(insight.get(key), max_length=512)
        if text is not None:
            result[key] = text
    source_metric_keys = insight.get("source_metric_keys")
    if isinstance(source_metric_keys, Sequence) and not isinstance(source_metric_keys, (str, bytes)):
        result["source_metric_keys"] = [
            text
            for text in (_safe_text(item, max_length=128) for item in source_metric_keys[:32])
            if text is not None
        ]
    related_not_causal = insight.get("related_not_causal")
    if isinstance(related_not_causal, bool):
        result["related_not_causal"] = related_not_causal
    return result or None


def _metric_values(metrics: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    return {
        metric["key"]: metric["value"]
        for metric in metrics
        if isinstance(metric.get("key"), str) and _safe_number(metric.get("value")) is not None
    }


def _ranking_fact(section: Mapping[str, Any]) -> dict[str, Any] | None:
    if section.get("type") not in _SIMPLE_SECTION_TYPES or section.get("type") == "status":
        return None
    numeric_items = [
        item
        for item in section.get("items", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("name"), str)
        and _safe_number(item.get("value")) is not None
    ]
    if not numeric_items:
        return None

    ranked = sorted(numeric_items, key=lambda item: float(item["value"]), reverse=True)
    values = [float(item["value"]) for item in numeric_items]
    total = sum(values)
    maximum = ranked[0]["value"]
    minimum = ranked[-1]["value"]
    top: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked[:10], start=1):
        entry: dict[str, Any] = {
            "rank": rank,
            "name": item["name"],
            "value": item["value"],
        }
        if total > 0:
            entry["share"] = _rounded(float(item["value"]) / total, 6)
        top.append(entry)

    return {
        "key": f"{section['key']}_ranking",
        "type": "ranking",
        "section_key": section["key"],
        "title": section["title"],
        "top": top,
        "maximum": maximum,
        "minimum": minimum,
        "gap": _rounded(float(maximum) - float(minimum), 6),
        "total": _rounded(total, 6),
    }


def _grouped_facts(section: Mapping[str, Any]) -> list[dict[str, Any]]:
    if section.get("type") != "grouped_bar":
        return []
    series_values: dict[str, list[dict[str, Any]]] = {}
    for item in section.get("items", []):
        if not isinstance(item, Mapping):
            continue
        category = item.get("category")
        if not isinstance(category, str):
            continue
        for series in item.get("series", []):
            if not isinstance(series, Mapping):
                continue
            key = series.get("key")
            label = series.get("label")
            value = _safe_number(series.get("value"))
            if not isinstance(key, str) or not isinstance(label, str) or value is None:
                continue
            series_values.setdefault(key, []).append(
                {"category": category, "label": label, "value": value}
            )

    facts: list[dict[str, Any]] = []
    for key, points in series_values.items():
        ranked = sorted(points, key=lambda point: float(point["value"]), reverse=True)
        values = [float(point["value"]) for point in points]
        facts.append(
            {
                "key": f"{section['key']}_{key}_comparison",
                "type": "group_comparison",
                "section_key": section["key"],
                "series_key": key,
                "series_label": ranked[0]["label"],
                "top": [
                    {
                        "rank": rank,
                        "category": point["category"],
                        "value": point["value"],
                    }
                    for rank, point in enumerate(ranked[:10], start=1)
                ],
                "maximum": ranked[0]["value"],
                "minimum": ranked[-1]["value"],
                "gap": _rounded(float(ranked[0]["value"]) - float(ranked[-1]["value"]), 6),
                "total": _rounded(sum(values), 6),
            }
        )

    for item in section.get("items", []):
        if not isinstance(item, Mapping):
            continue
        series = [point for point in item.get("series", []) if isinstance(point, Mapping)]
        numeric = [point for point in series if _safe_number(point.get("value")) is not None]
        if len(numeric) < 2:
            continue
        ordered = sorted(numeric, key=lambda point: float(point["value"]), reverse=True)
        facts.append(
            {
                "key": f"{section['key']}_{item['category']}_group_gap",
                "type": "group_difference",
                "section_key": section["key"],
                "category": item["category"],
                "higher": ordered[0].get("key"),
                "lower": ordered[-1].get("key"),
                "gap": _rounded(float(ordered[0]["value"]) - float(ordered[-1]["value"]), 6),
            }
        )
    return facts


def derive_facts(
    metrics: Sequence[Mapping[str, Any]], sections: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Derive bounded arithmetic facts from already validated aggregate data."""

    facts: list[dict[str, Any]] = []
    values = _metric_values(metrics)
    charges = values.get("avg_charges")
    costs = values.get("avg_costs")
    if charges is not None and costs is not None:
        gap = float(charges) - float(costs)
        facts.append(
            {
                "key": "charge_cost_gap",
                "type": "difference",
                "value": _rounded(gap, 2),
                "unit": "same_as_source_metrics",
                "source_metric_keys": ["avg_charges", "avg_costs"],
            }
        )
        if float(costs) != 0:
            facts.append(
                {
                    "key": "charge_cost_ratio",
                    "type": "ratio",
                    "value": _rounded(float(charges) / float(costs), 4),
                    "unit": "times",
                    "source_metric_keys": ["avg_charges", "avg_costs"],
                }
            )

    for section in sections:
        fact = _ranking_fact(section)
        if fact is not None:
            facts.append(fact)
        facts.extend(_grouped_facts(section))
        if section.get("type") == "scatter":
            points = [item for item in section.get("items", []) if isinstance(item, Mapping)]
            if points:
                facts.append(
                    {
                        "key": f"{section['key']}_point_count",
                        "type": "point_count",
                        "value": len(points),
                        "section_key": section["key"],
                        "limitation": "仅列出汇总点，不能据此认定统计相关或因果关系。",
                    }
                )

    return facts[:_MAX_FACTS]


def build_safe_evidence(tool: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Project one analytics snapshot into the model-facing evidence schema."""

    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot must be an object")
    safe_tool = _required_text(tool, "tool")
    title = _required_text(snapshot.get("title"), "title")
    description = _required_text(snapshot.get("description"), "description")
    data_version = _required_text(snapshot.get("data_version"), "data_version")

    raw_metrics = snapshot.get("metrics")
    raw_sections = snapshot.get("sections")
    if not isinstance(raw_metrics, Sequence) or isinstance(raw_metrics, (str, bytes)):
        raise ValueError("snapshot.metrics must be a list")
    if not isinstance(raw_sections, Sequence) or isinstance(raw_sections, (str, bytes)):
        raise ValueError("snapshot.sections must be a list")

    metrics = [_safe_metric(item) for item in raw_metrics if isinstance(item, Mapping)]
    sections = [_safe_section(item) for item in raw_sections if isinstance(item, Mapping)]
    insights: list[dict[str, Any]] = []
    raw_insights = snapshot.get("insights")
    if isinstance(raw_insights, Sequence) and not isinstance(raw_insights, (str, bytes)):
        insights = [
            safe_insight
            for item in raw_insights[:_MAX_INSIGHTS]
            if isinstance(item, Mapping)
            for safe_insight in [_safe_insight(item)]
            if safe_insight is not None
        ]

    boundaries: list[str] = []
    for section in sections:
        visual = section.get("visual")
        if isinstance(visual, Mapping):
            summary = visual.get("summary")
            if isinstance(summary, Mapping):
                boundary = _safe_text(summary.get("boundary"))
                if boundary and boundary not in boundaries:
                    boundaries.append(boundary)
    for insight in insights:
        boundary = insight.get("boundary")
        if isinstance(boundary, str) and boundary not in boundaries:
            boundaries.append(boundary)

    generated_at = _safe_text(snapshot.get("generated_at"), max_length=128)
    evidence: dict[str, Any] = {
        "tool": safe_tool,
        "title": title,
        "description": description,
        "data_version": data_version,
        "boundary": SAFE_BOUNDARY,
        "metrics": metrics,
        "sections": sections,
        "insights": insights,
        "derived_facts": derive_facts(metrics, sections),
        "limitations": [
            "仅使用已发布的群体汇总和工具返回字段。",
            "不包含患者级明细，不支持个体判断、诊疗建议或因果结论。",
        ],
    }
    if generated_at is not None:
        evidence["generated_at"] = generated_at
    if boundaries:
        evidence["source_boundaries"] = boundaries
    return evidence


def _has_term(question: str, terms: Sequence[str]) -> bool:
    lowered = question.lower()
    return any(term.lower() in lowered for term in terms)


def is_patient_level_question(question: str) -> bool:
    """Return true only for an individual-patient or identifier request."""

    if not isinstance(question, str):
        return False
    return _PATIENT_LEVEL_QUESTION_PATTERN.search(question.strip()) is not None


def _unsafe_question(question: str) -> bool:
    return is_patient_level_question(question) or _has_term(question, _UNSAFE_TERMS) or (
        "预测" in question and _has_term(question, ("患者", "病人", "个人", "张三", "某人"))
    )


def _topic_from_question(question: str) -> set[str]:
    topics: set[str] = set()
    if _has_term(question, ("整体", "运营", "经营", "总体", "概况", "全局")):
        topics.add("overall")
    if "医院" in question or "机构" in question:
        topics.add("hospital")
    if _has_term(question, ("疾病", "诊断", "病种")):
        topics.add("disease")
    if _has_term(question, ("群体", "人群", "年龄", "性别", "队列", "入院方式")):
        topics.add("cohort")
    if _has_term(question, ("费用", "收费", "成本", "花费", "高费用")):
        topics.add("cost")
    if _has_term(question, ("风险", "严重程度", "重症", "死亡", "高风险")):
        topics.add("risk")
    if _has_term(question, ("支付", "付款", "医保", "自费")):
        topics.add("payment")
    if _has_term(question, ("模型", "准确率", "精确率", "召回率", "AUC", "F1")):
        topics.add("model")
    return topics


def is_simple_conversation(question: str) -> bool:
    """Return true only for explicit, non-analytic conversational intents."""

    if not isinstance(question, str):
        return False
    if _topic_from_question(question):
        return False
    normalized = question.strip().lower().strip(_CONVERSATION_EDGE_PUNCTUATION)
    return normalized in _SIMPLE_CONVERSATION_PHRASES


def assess_question_scope(question: str) -> dict[str, Any] | None:
    """Classify requests that do not need a data tool at all.

    A non-None result is an intrinsic safety/capability decision.  Returning
    None means the question is not deterministically unsupported/unsafe. The
    normal router must continue, even when the topic is vague or unknown.
    """

    question = question.strip()
    if _unsafe_question(question):
        return {
            "status": "unsafe",
            "answerable": False,
            "reason": "问题涉及患者级判断、诊疗建议、个体预测或受限查询。",
            "limitations": ["当前白名单工具只提供群体汇总，不能支持该请求。"],
        }
    if _has_term(question, _TREND_TERMS):
        return {
            "status": "unsupported",
            "answerable": False,
            "reason": "当前工具提供版本化汇总快照，不提供按时间的历史序列。",
            "limitations": ["无法据此回答同比、环比或时间趋势问题。"],
        }
    if _has_term(question, _CAUSAL_TERMS):
        return {
            "status": "unsupported",
            "answerable": False,
            "reason": "当前聚合数据不能证明因果关系或解释费用、风险等现象的原因。",
            "limitations": ["只能描述已有汇总差异，不能把观察性数据解释为因果结论。"],
        }
    return None


def _evidence_capabilities(evidence: Mapping[str, Any]) -> set[str]:
    capabilities: set[str] = set()
    topic = _TOOL_TOPIC.get(evidence.get("tool"))
    if topic:
        capabilities.add(topic)
    for section in evidence.get("sections", []):
        if isinstance(section, Mapping):
            key = section.get("key")
            section_type = section.get("type")
            if isinstance(key, str):
                capabilities.add(key)
            if section_type == "scatter":
                capabilities.add("scatter")
            if section_type == "heatmap":
                capabilities.add("heatmap")
    return capabilities


def _section_items(evidences: Sequence[Mapping[str, Any]], predicate: Any) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for evidence in evidences:
        for section in evidence.get("sections", []):
            if isinstance(section, Mapping) and predicate(section):
                result.extend(
                    item
                    for item in section.get("items", [])
                    if isinstance(item, Mapping)
                )
    return result


def assess_answerability(question: str, evidences: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify what can safely be answered from the selected aggregate data."""

    question = question.strip()
    intrinsic_answerability = assess_question_scope(question)
    if intrinsic_answerability is not None:
        return intrinsic_answerability

    topics = _topic_from_question(question)
    evidence_topics = {
        topic
        for evidence in evidences
        for topic in [_TOOL_TOPIC.get(evidence.get("tool"))]
        if topic is not None
    }
    capabilities = {
        capability
        for evidence in evidences
        for capability in _evidence_capabilities(evidence)
    }
    limitations: list[str] = []

    if not evidences or not any(
        evidence.get("metrics") or evidence.get("sections") for evidence in evidences
    ):
        return {
            "status": "unsupported",
            "answerable": False,
            "reason": "没有可用的已验证汇总证据。",
            "limitations": ["当前工具结果不足以支持可靠回答。"],
        }
    if topics and not (topics & evidence_topics):
        return {
            "status": "unsupported",
            "answerable": False,
            "reason": "已选工具与问题主题不匹配，现有证据没有相应汇总。",
            "limitations": ["不能用无关主题的数据替代所要求的分析。"],
        }
    if not topics:
        return {
            "status": "unsupported",
            "answerable": False,
            "reason": "问题主题无法映射到当前八个白名单汇总工具。",
            "limitations": ["请改为询问运营、医院、疾病、群体、费用、风险、支付或模型汇总。"],
        }

    if _has_term(question, _RANKING_TERMS):
        if "医院" in question:
            required = {"ranking", "hospital_top10", "facility_metric_comparison"}
        elif _has_term(question, ("疾病", "病种")):
            required = {"top10", "disease_top10"}
        else:
            required = {"ranking", "top10", "payment", "diseases"}
        if not (capabilities & required):
            return {
                "status": "unsupported",
                "answerable": False,
                "reason": "当前证据没有支持排名的明细汇总。",
                "limitations": ["不能从单个总量指标推导排名。"],
            }

    if _has_term(question, _STRUCTURE_TERMS):
        if not any(
            capability in capabilities
            for capability in ("payment", "diseases", "age", "gender", "severity", "top10", "disease_top10")
        ):
            return {
                "status": "unsupported",
                "answerable": False,
                "reason": "当前证据没有可用于结构或分布分析的分组明细。",
                "limitations": ["不能从整体指标臆测结构特征。"],
            }

    if _has_term(question, _RELATION_TERMS):
        scatter_sections = [
            section
            for evidence in evidences
            for section in evidence.get("sections", [])
            if isinstance(section, Mapping) and section.get("type") == "scatter"
        ]
        if "医院" in question or "机构" in question:
            hospital_sections = [
                section
                for section in scatter_sections
                if any(
                    marker in str(section.get("key", "")).lower()
                    for marker in ("facility", "hospital", "医院")
                )
            ]
            if hospital_sections:
                scatter_sections = hospital_sections
        if not scatter_sections:
            return {
                "status": "unsupported",
                "answerable": False,
                "reason": "当前工具没有返回可用于关系比较的配对汇总数据。",
                "limitations": ["不能从两个孤立指标断言相关关系。"],
            }
        point_count = max(len(section.get("items", [])) for section in scatter_sections)
        if point_count < 3 or _has_term(question, _CAUSAL_TERMS):
            limitations.append("现有配对汇总点有限，只能描述差异，不能认定统计相关或因果关系。")

    if _has_term(question, _CAUSAL_TERMS):
        limitations.append("工具返回的是观察性汇总，无法解释原因或证明因果关系。")

    if _has_term(question, _FOCUS_TERMS) and _has_term(question, ("疾病", "病种")):
        if not (capabilities & {"top10", "disease_top10", "diseases"}):
            return {
                "status": "unsupported",
                "answerable": False,
                "reason": "当前证据没有疾病层面的重点项汇总。",
                "limitations": ["不能凭整体指标指定重点疾病。"],
            }
        limitations.append("重点关注只能依据现有汇总中的规模、风险或费用信号，不能作医疗判断。")

    if len(topics & {"cost", "risk"}) == 2 or (
        _has_term(question, ("结合", "同时")) and len(topics) >= 2
    ):
        has_joint_cost_risk_section = any(
            isinstance(section, Mapping)
            and "cost" in str(section.get("key", "")).lower()
            and "risk" in str(section.get("key", "")).lower()
            for evidence in evidences
            for section in evidence.get("sections", [])
        )
        if not has_joint_cost_risk_section:
            limitations.append("当前工具没有费用与风险在同一分组粒度上的联合汇总，只能分别描述两侧信号。")

    status = "partially_answerable" if limitations else "answerable"
    result: dict[str, Any] = {
        "status": status,
        "answerable": status == "answerable",
        "supported_topics": sorted(topics & evidence_topics),
    }
    if limitations:
        result["limitations"] = limitations
        result["reason"] = "可以回答可验证的汇总部分，但问题包含当前数据无法证明的部分。"
    else:
        result["reason"] = "问题可以在当前已验证汇总范围内回答。"
    return result


def validate_answer_grounding(
    answer: str, evidences: Sequence[Mapping[str, Any]], answerability: Mapping[str, Any]
) -> bool:
    """Perform a deliberately small final-answer grounding check.

    This is not a natural-language fact checker.  It catches empty/suspicious
    output, requires a limitation statement for refusal cases, and otherwise
    requires one source anchor or a number present in the safe evidence.
    """

    if not isinstance(answer, str) or not answer.strip():
        return False
    text = answer.strip()
    lowered = text.lower()
    if any(marker in lowered for marker in ("<script", "javascript:", "select * from", "drop table")):
        return False

    status = answerability.get("status")
    if status in {"unsafe", "unsupported"}:
        return _has_term(text, ("无法", "不能", "不支持", "不包含", "当前数据", "仅提供"))

    anchors: set[str] = set()
    evidence_numbers: list[float] = []
    for evidence in evidences:
        for key in ("tool", "title", "description"):
            value = evidence.get(key)
            if isinstance(value, str) and len(value) >= 2:
                anchors.add(value.lower())
        for metric in evidence.get("metrics", []):
            if isinstance(metric, Mapping):
                for key in ("key", "label"):
                    value = metric.get(key)
                    if isinstance(value, str) and len(value) >= 2:
                        anchors.add(value.lower())
                number = _safe_number(metric.get("value"))
                if number is not None:
                    evidence_numbers.append(float(number))
        for section in evidence.get("sections", []):
            if not isinstance(section, Mapping):
                continue
            for key in ("key", "title"):
                value = section.get(key)
                if isinstance(value, str) and len(value) >= 2:
                    anchors.add(value.lower())
            for item in section.get("items", []):
                if not isinstance(item, Mapping):
                    continue
                for key in ("name", "category", "x_label", "y_label"):
                    value = item.get(key)
                    if isinstance(value, str) and len(value) >= 2:
                        anchors.add(value.lower())
                for value in item.values():
                    number = _safe_number(value)
                    if number is not None:
                        evidence_numbers.append(float(number))
        for fact in evidence.get("derived_facts", []):
            if not isinstance(fact, Mapping):
                continue
            for value in fact.values():
                number = _safe_number(value)
                if number is not None:
                    evidence_numbers.append(float(number))

    if any(anchor in lowered for anchor in anchors):
        return True
    for token in _NUMBER_PATTERN.findall(text):
        try:
            value = float(token)
        except ValueError:
            continue
        if any(
            abs(value - source_value) <= max(0.02, abs(source_value) * 0.005)
            or abs(value / 100 - source_value) <= max(0.0002, abs(source_value) * 0.005)
            for source_value in evidence_numbers
        ):
            return True
    return False


__all__ = [
    "ANSWERABILITY_STATUSES",
    "SAFE_BOUNDARY",
    "assess_answerability",
    "assess_question_scope",
    "build_safe_evidence",
    "derive_facts",
    "is_simple_conversation",
    "is_patient_level_question",
    "validate_answer_grounding",
]
