"""The single validation seam for the published analytics snapshot.

The data publisher and the read API are two adapters around the same public
interface.  Keeping the structural rules here prevents a fixture, a JSON
artifact, and a MySQL row from silently acquiring different meanings.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from .disease_rules import is_non_disease_diagnosis


PAYLOAD_KEYS = frozenset(
    {
        "title",
        "description",
        "options",
        "filters",
        "metrics",
        "sections",
        "insights",
    }
)
PAYLOAD_REQUIRED_KEYS = frozenset({"title", "description", "metrics", "sections"})
SECTION_TYPES = frozenset(
    {
        "bar",
        "pie",
        "table",
        "status",
        "grouped_bar",
        "scatter",
        "heatmap",
        "correlation",
    }
)
COMPLEX_SECTION_TYPES = frozenset(
    {"grouped_bar", "scatter", "heatmap", "correlation"}
)
DOCUMENT_KEYS = frozenset({"data_version", "generated_at", "records", "input"})

VISUAL_KEYS = frozenset(
    {
        "question",
        "x_label",
        "y_label",
        "unit",
        "legend",
        "tooltip_fields",
        "summary",
        "fallback",
        "empty",
    }
)
VISUAL_SUMMARY_KEYS = frozenset(
    {
        "text",
        "source_metric_keys",
        "source_section",
        "data_version",
        "generated_at",
        "boundary",
        "related_not_causal",
    }
)
INSIGHT_KEYS = frozenset(
    {
        "key",
        "title",
        "summary",
        "level",
        "source_section",
        "source_metric_keys",
        "data_version",
        "generated_at",
        "boundary",
        "related_not_causal",
    }
)
VISUAL_UNITS = frozenset({"条", "天", "美元", "美元/天", "%", "相关系数"})
LEGEND_STYLES = frozenset(
    {"solid", "pattern", "shape", "numeric", "numeric-gradient"}
)
INSIGHT_LEVELS = frozenset({"info", "notice", "warning"})
GROUPED_BAR_ITEM_KEYS = frozenset({"category", "series"})
GROUPED_BAR_SERIES_KEYS = frozenset({"key", "label", "value"})
SCATTER_ITEM_KEYS = frozenset(
    {"name", "x", "y", "size", "group", "cost", "high_cost_rate"}
)
HEATMAP_ITEM_KEYS = frozenset(
    {"x_label", "y_label", "value", "unit", "numerator", "denominator", "high_risk_rate"}
)
CORRELATION_ITEM_KEYS = frozenset(
    {
        "x_key",
        "x_label",
        "y_key",
        "y_label",
        "coefficient",
        "sample_size",
        "method",
    }
)


class SnapshotContractError(ValueError):
    """Raised when a snapshot cannot satisfy the public interface."""


def _fail(message: str) -> None:
    raise SnapshotContractError(message)


def _string(value: Any, field: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _fail(f"{field} 必须是非空、无首尾空白的字符串")
    if max_length is not None and len(value) > max_length:
        _fail(f"{field} 长度不能超过 {max_length}")
    return value


def validate_data_version(value: Any) -> str:
    version = _string(value, "data_version", max_length=191)
    if not version.isascii() or any(character.isspace() for character in version):
        _fail("data_version 必须是无空白 ASCII 字符串")
    return version


def normalize_utc_timestamp(value: Any) -> str:
    """Return the canonical UTC representation used by the API."""

    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            # MySQL DATETIME(6) is stored as UTC by the publisher.
            parsed = parsed.replace(tzinfo=UTC)
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise SnapshotContractError("generated_at 必须是 ISO-8601 UTC 时间") from error
    else:
        _fail("generated_at 必须使用以 Z 结尾的 ISO-8601 UTC 时间")

    if parsed.tzinfo is None:
        _fail("generated_at 必须包含 UTC 时区")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _json_value(value: Any, field: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise SnapshotContractError(f"{field} 不是合法 JSON 值") from error


def _number(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{field} 必须是数字")
    if isinstance(value, float) and not math.isfinite(value):
        _fail(f"{field} 不能是 NaN 或无穷大")


def _nonnegative_number(value: Any, field: str) -> None:
    _number(value, field)
    if value < 0:
        _fail(f"{field} 不能是负数")


def _string_list(
    value: Any,
    field: str,
    *,
    allowed: set[str] | frozenset[str] | None = None,
    min_length: int = 1,
    max_length: int = 16,
) -> list[str]:
    if not isinstance(value, list) or not min_length <= len(value) <= max_length:
        _fail(f"{field} 必须是 {min_length}—{max_length} 项字符串数组")
    result: list[str] = []
    for index, item in enumerate(value):
        item_field = f"{field}[{index}]"
        result.append(_string(item, item_field, max_length=128))
    if len(set(result)) != len(result):
        _fail(f"{field} 不能包含重复值")
    if allowed is not None:
        unknown = sorted(set(result) - set(allowed))
        if unknown:
            _fail(f"{field} 含有未冻结值: {', '.join(unknown)}")
    return result


def _object_keys(value: dict, allowed: set[str] | frozenset[str], field: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        _fail(f"{field} 含有未冻结字段: {', '.join(unknown)}")


def _validate_options(options: Any) -> None:
    if not isinstance(options, dict):
        _fail("payload.options 必须是对象")
    for name, values in options.items():
        _string(name, "options key", max_length=64)
        # Page filters use arrays of {value, label} or strings.  Model
        # metadata is kept under the same non-executable JSON object because
        # the snapshot payload has no second metadata channel.
        if isinstance(values, list):
            for index, item in enumerate(values):
                item_field = f"options.{name}[{index}]"
                if isinstance(item, dict):
                    _object_keys(item, {"value", "label"}, item_field)
                    _string(item.get("value"), f"{item_field}.value")
                    _string(item.get("label"), f"{item_field}.label")
                elif isinstance(item, str):
                    _string(item, item_field)
                else:
                    _fail(f"{item_field} 必须是字符串或 value/label 对象")
        else:
            _json_value(values, f"options.{name}")


def _validate_filters(filters: Any) -> None:
    if not isinstance(filters, dict):
        _fail("payload.filters 必须是对象")
    for name, value in filters.items():
        _string(name, "filters key", max_length=64)
        _string(value, f"filters.{name}")


def _validate_metrics(metrics: Any) -> None:
    if not isinstance(metrics, list):
        _fail("payload.metrics 必须是数组")
    for index, metric in enumerate(metrics):
        field = f"metrics[{index}]"
        if not isinstance(metric, dict):
            _fail(f"{field} 必须是对象")
        _object_keys(metric, {"key", "label", "value", "unit"}, field)
        for name in ("key", "label", "unit"):
            _string(metric.get(name), f"{field}.{name}")
        _number(metric.get("value"), f"{field}.value")


def _validate_legend(value: Any, field: str) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        _fail(f"{field} 必须是 1—3 项图例数组")
    for index, item in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(item, dict):
            _fail(f"{item_field} 必须是对象")
        _object_keys(item, {"key", "label", "style"}, item_field)
        _string(item.get("key"), f"{item_field}.key", max_length=64)
        _string(item.get("label"), f"{item_field}.label", max_length=128)
        style = item.get("style")
        if style not in LEGEND_STYLES:
            _fail(f"{item_field}.style 不是冻结的图例样式")


def _validate_visual_summary(summary: Any, section_key: str, field: str) -> None:
    if not isinstance(summary, dict):
        _fail(f"{field} 必须是对象")
    _object_keys(summary, VISUAL_SUMMARY_KEYS, field)
    _string(summary.get("text"), f"{field}.text", max_length=512)
    _string_list(summary.get("source_metric_keys"), f"{field}.source_metric_keys")
    if summary.get("source_section") != section_key:
        _fail(f"{field}.source_section 必须指向当前 section")
    validate_data_version(summary.get("data_version"))
    normalize_utc_timestamp(summary.get("generated_at"))
    _string(summary.get("boundary"), f"{field}.boundary", max_length=512)
    if not isinstance(summary.get("related_not_causal"), bool):
        _fail(f"{field}.related_not_causal 必须是布尔值")


def _validate_fallback(value: Any, field: str) -> None:
    if not isinstance(value, dict):
        _fail(f"{field} 必须是对象")
    _object_keys(value, {"type", "columns"}, field)
    if value.get("type") != "table":
        _fail(f"{field}.type 只能是 table")
    _string_list(value.get("columns"), f"{field}.columns", max_length=12)


def _validate_empty(value: Any, field: str) -> None:
    if not isinstance(value, dict):
        _fail(f"{field} 必须是对象")
    _object_keys(value, {"title", "text"}, field)
    _string(value.get("title"), f"{field}.title", max_length=128)
    _string(value.get("text"), f"{field}.text", max_length=512)


def _validate_visual(visual: Any, section_key: str, section_type: str) -> None:
    if not isinstance(visual, dict):
        _fail(f"sections.{section_key}.visual 必须是对象")
    _object_keys(visual, VISUAL_KEYS, f"sections.{section_key}.visual")
    field = f"sections.{section_key}.visual"
    _string(visual.get("question"), f"{field}.question", max_length=256)
    _string(visual.get("x_label"), f"{field}.x_label", max_length=128)
    _string(visual.get("y_label"), f"{field}.y_label", max_length=128)
    unit = visual.get("unit")
    if unit not in VISUAL_UNITS:
        _fail(f"{field}.unit 不是冻结的展示单位")
    _validate_legend(visual.get("legend"), f"{field}.legend")
    allowed_tooltips = {
        "category",
        "series_label",
        "value",
        "unit",
        "name",
        "x",
        "y",
        "size",
        "group",
        "cost",
        "high_cost_rate",
        "high_risk_rate",
        "x_label",
        "y_label",
        "numerator",
        "denominator",
        "coefficient",
        "sample_size",
        "method",
    }
    _string_list(
        visual.get("tooltip_fields"),
        f"{field}.tooltip_fields",
        allowed=allowed_tooltips,
        max_length=12,
    )
    _validate_visual_summary(visual.get("summary"), section_key, f"{field}.summary")
    _validate_fallback(visual.get("fallback"), f"{field}.fallback")
    _validate_empty(visual.get("empty"), f"{field}.empty")


def _validate_grouped_bar_items(items: list[Any], field: str) -> None:
    if len(items) > 15:
        _fail(f"{field} 最多允许 15 个类别")
    for index, item in enumerate(items):
        item_field = f"{field}[{index}]"
        if not isinstance(item, dict):
            _fail(f"{item_field} 必须是对象")
        _object_keys(item, GROUPED_BAR_ITEM_KEYS, item_field)
        _string(item.get("category"), f"{item_field}.category", max_length=128)
        series = item.get("series")
        if not isinstance(series, list) or not 1 <= len(series) <= 3:
            _fail(f"{item_field}.series 必须是 1—3 项数组")
        series_keys: set[str] = set()
        for series_index, value in enumerate(series):
            series_field = f"{item_field}.series[{series_index}]"
            if not isinstance(value, dict):
                _fail(f"{series_field} 必须是对象")
            _object_keys(value, GROUPED_BAR_SERIES_KEYS, series_field)
            key = _string(value.get("key"), f"{series_field}.key", max_length=64)
            if key in series_keys:
                _fail(f"{series_field}.key 不能重复")
            series_keys.add(key)
            _string(value.get("label"), f"{series_field}.label", max_length=128)
            _nonnegative_number(value.get("value"), f"{series_field}.value")


def _validate_scatter_items(items: list[Any], field: str) -> None:
    if len(items) > 500:
        _fail(f"{field} 最多允许 500 个点")
    for index, item in enumerate(items):
        item_field = f"{field}[{index}]"
        if not isinstance(item, dict):
            _fail(f"{item_field} 必须是对象")
        _object_keys(item, SCATTER_ITEM_KEYS, item_field)
        _string(item.get("name"), f"{item_field}.name", max_length=191)
        for name in ("x", "y", "size"):
            _nonnegative_number(item.get(name), f"{item_field}.{name}")
        group = item.get("group")
        if isinstance(group, str):
            _string(group, f"{item_field}.group", max_length=128)
        else:
            _number(group, f"{item_field}.group")
        if "cost" in item:
            _nonnegative_number(item["cost"], f"{item_field}.cost")
        if "high_cost_rate" in item:
            _number(item["high_cost_rate"], f"{item_field}.high_cost_rate")
            if not 0 <= item["high_cost_rate"] <= 1:
                _fail(f"{item_field}.high_cost_rate 必须在 0 到 1 之间")


def _validate_heatmap_items(items: list[Any], field: str) -> None:
    if len(items) > 100:
        _fail(f"{field} 最多允许 100 个格子")
    for index, item in enumerate(items):
        item_field = f"{field}[{index}]"
        if not isinstance(item, dict):
            _fail(f"{item_field} 必须是对象")
        _object_keys(item, HEATMAP_ITEM_KEYS, item_field)
        _string(item.get("x_label"), f"{item_field}.x_label", max_length=128)
        _string(item.get("y_label"), f"{item_field}.y_label", max_length=128)
        _nonnegative_number(item.get("value"), f"{item_field}.value")
        if item.get("unit") not in VISUAL_UNITS:
            _fail(f"{item_field}.unit 不是冻结的展示单位")
        for name in ("numerator", "denominator"):
            if name in item:
                _nonnegative_number(item[name], f"{item_field}.{name}")
        if "high_risk_rate" in item:
            _number(item["high_risk_rate"], f"{item_field}.high_risk_rate")
            if not 0 <= item["high_risk_rate"] <= 1:
                _fail(f"{item_field}.high_risk_rate 必须在 0 到 1 之间")


def _validate_correlation_items(items: list[Any], field: str) -> None:
    if len(items) > 12:
        _fail(f"{field} 最多允许 12 组相关系数")
    seen_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        item_field = f"{field}[{index}]"
        if not isinstance(item, dict):
            _fail(f"{item_field} 必须是对象")
        _object_keys(item, CORRELATION_ITEM_KEYS, item_field)
        x_key = _string(item.get("x_key"), f"{item_field}.x_key", max_length=64)
        y_key = _string(item.get("y_key"), f"{item_field}.y_key", max_length=64)
        _string(item.get("x_label"), f"{item_field}.x_label", max_length=128)
        _string(item.get("y_label"), f"{item_field}.y_label", max_length=128)
        if x_key == y_key:
            _fail(f"{item_field} 不能比较同一指标")
        pair = tuple(sorted((x_key, y_key)))
        if pair in seen_pairs:
            _fail(f"{item_field} 不能重复同一指标组合")
        seen_pairs.add(pair)
        coefficient = item.get("coefficient")
        _number(coefficient, f"{item_field}.coefficient")
        if not -1 <= coefficient <= 1:
            _fail(f"{item_field}.coefficient 必须在 -1 到 1 之间")
        sample_size = item.get("sample_size")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int):
            _fail(f"{item_field}.sample_size 必须是正整数")
        if sample_size < 2:
            _fail(f"{item_field}.sample_size 必须至少为 2")
        if item.get("method") != "pearson":
            _fail(f"{item_field}.method 只能是 pearson")


def _validate_insights(insights: Any, section_keys: set[str]) -> None:
    if not isinstance(insights, list) or len(insights) > 8:
        _fail("payload.insights 必须是最多 8 项数组")
    seen: set[str] = set()
    for index, insight in enumerate(insights):
        field = f"insights[{index}]"
        if not isinstance(insight, dict):
            _fail(f"{field} 必须是对象")
        _object_keys(insight, INSIGHT_KEYS, field)
        key = _string(insight.get("key"), f"{field}.key", max_length=64)
        if key in seen:
            _fail(f"{field}.key 不能重复")
        seen.add(key)
        _string(insight.get("title"), f"{field}.title", max_length=128)
        _string(insight.get("summary"), f"{field}.summary", max_length=512)
        if insight.get("level") not in INSIGHT_LEVELS:
            _fail(f"{field}.level 不是冻结的洞察级别")
        source_section = _string(
            insight.get("source_section"), f"{field}.source_section", max_length=64
        )
        if source_section not in section_keys:
            _fail(f"{field}.source_section 必须指向当前 section")
        _string_list(insight.get("source_metric_keys"), f"{field}.source_metric_keys")
        validate_data_version(insight.get("data_version"))
        normalize_utc_timestamp(insight.get("generated_at"))
        _string(insight.get("boundary"), f"{field}.boundary", max_length=512)
        if not isinstance(insight.get("related_not_causal"), bool):
            _fail(f"{field}.related_not_causal 必须是布尔值")


def _validate_sections(sections: Any) -> None:
    if not isinstance(sections, list):
        _fail("payload.sections 必须是数组")
    section_keys: set[str] = set()
    for index, section in enumerate(sections):
        field = f"sections[{index}]"
        if not isinstance(section, dict):
            _fail(f"{field} 必须是对象")
        section_key = _string(section.get("key"), f"{field}.key")
        if section_key in section_keys:
            _fail(f"{field}.key 不能重复")
        section_keys.add(section_key)
        _string(section.get("title"), f"{field}.title")
        section_type = section.get("type")
        if section_type not in SECTION_TYPES:
            _fail(
                f"{field}.type 只能是 bar、pie、table、status、grouped_bar、"
                "scatter、heatmap 或 correlation"
            )
        allowed_section_keys = {"key", "title", "type", "items"}
        if section_type in COMPLEX_SECTION_TYPES:
            allowed_section_keys.add("visual")
        _object_keys(section, allowed_section_keys, field)
        items = section.get("items")
        if not isinstance(items, list):
            _fail(f"{field}.items 必须是数组")
        if section_type in COMPLEX_SECTION_TYPES:
            _validate_visual(section.get("visual"), section_key, section_type)
            if section_type == "grouped_bar":
                _validate_grouped_bar_items(items, f"{field}.items")
            elif section_type == "scatter":
                _validate_scatter_items(items, f"{field}.items")
            elif section_type == "heatmap":
                _validate_heatmap_items(items, f"{field}.items")
            else:
                _validate_correlation_items(items, f"{field}.items")
            continue
        for item_index, item in enumerate(items):
            item_field = f"{field}.items[{item_index}]"
            if not isinstance(item, dict):
                _fail(f"{item_field} 必须是对象")
            _object_keys(item, {"name", "value"}, item_field)
            _string(item.get("name"), f"{item_field}.name")
            if section_type == "status":
                _string(item.get("value"), f"{item_field}.value")
            else:
                _number(item.get("value"), f"{item_field}.value")


def validate_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        _fail("payload 必须是对象")
    _object_keys(payload, PAYLOAD_KEYS, "payload")
    missing = sorted(PAYLOAD_REQUIRED_KEYS - set(payload))
    if missing:
        _fail(f"payload 缺少字段: {', '.join(missing)}")
    _string(payload.get("title"), "payload.title")
    _string(payload.get("description"), "payload.description")
    if "options" in payload:
        _validate_options(payload["options"])
    if "filters" in payload:
        _validate_filters(payload["filters"])
    _validate_metrics(payload["metrics"])
    _validate_sections(payload["sections"])
    if "insights" in payload:
        section_keys = {section["key"] for section in payload["sections"]}
        _validate_insights(payload["insights"], section_keys)
    _json_value(payload, "payload")
    return payload


def validate_disease_semantics(
    payload: dict, module_key: str = "", entity_key: str = ""
) -> dict:
    """Reject non-disease diagnosis labels from every disease-facing section."""

    options = payload.get("options") or {}
    for option in options.get("diagnoses", []):
        values = option.values() if isinstance(option, dict) else (option,)
        if any(is_non_disease_diagnosis(value) for value in values):
            _fail("疾病选项不能包含非疾病标签")

    if module_key == "diseases" and entity_key.startswith("profile:"):
        if is_non_disease_diagnosis(payload.get("title")):
            _fail("疾病画像不能使用非疾病标签")

    for section in payload.get("sections", []):
        key = str(section.get("key") or "").lower()
        title = str(section.get("title") or "")
        is_disease_section = (
            "disease" in key
            or "diagnos" in key
            or key in {"diseases", "top10"}
            or "疾病" in title
            or "诊断" in title
        )
        if not is_disease_section:
            continue
        for item in section.get("items", []):
            if not isinstance(item, dict):
                continue
            candidates = [item.get("name"), item.get("category")]
            series = item.get("series")
            if isinstance(series, list):
                candidates.extend(
                    entry.get("label")
                    for entry in series
                    if isinstance(entry, dict)
                )
            if any(is_non_disease_diagnosis(value) for value in candidates):
                _fail("疾病分析结果不能包含非疾病标签")
    return payload


def validate_payload_metadata(payload: dict, data_version: Any, generated_at: Any) -> None:
    """Ensure nested insight metadata cannot drift from the snapshot envelope."""

    expected_version = validate_data_version(data_version)
    expected_timestamp = normalize_utc_timestamp(generated_at)
    for insight in payload.get("insights", []):
        if insight["data_version"] != expected_version:
            _fail("insight.data_version 必须与快照 data_version 一致")
        if normalize_utc_timestamp(insight["generated_at"]) != expected_timestamp:
            _fail("insight.generated_at 必须与快照 generated_at 一致")
    for section in payload.get("sections", []):
        if section["type"] not in COMPLEX_SECTION_TYPES:
            continue
        summary = section["visual"]["summary"]
        if summary["data_version"] != expected_version:
            _fail("visual.summary.data_version 必须与快照 data_version 一致")
        if normalize_utc_timestamp(summary["generated_at"]) != expected_timestamp:
            _fail("visual.summary.generated_at 必须与快照 generated_at 一致")


def validate_snapshot_document(document: Any) -> dict:
    if not isinstance(document, dict):
        _fail("快照文档必须是对象")
    _object_keys(document, DOCUMENT_KEYS, "快照文档")
    validate_data_version(document.get("data_version"))
    normalize_utc_timestamp(document.get("generated_at"))
    records = document.get("records")
    if not isinstance(records, list) or not records:
        _fail("records 必须是非空数组")

    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        field = f"records[{index}]"
        if not isinstance(record, dict):
            _fail(f"{field} 必须是对象")
        _object_keys(record, {"module_key", "entity_key", "payload"}, field)
        module_key = _string(record.get("module_key"), f"{field}.module_key", max_length=64)
        entity_key = _string(record.get("entity_key"), f"{field}.entity_key", max_length=191)
        if any(character in "\r\n\t" for character in module_key):
            _fail(f"{field}.module_key 不能含控制空白")
        if any(character in "\r\n\t" for character in entity_key):
            _fail(f"{field}.entity_key 不能含控制空白")
        key = (module_key, entity_key)
        if key in seen:
            _fail(f"快照主键重复: {key}")
        payload = validate_payload(record.get("payload"))
        validate_disease_semantics(payload, module_key, entity_key)
        validate_payload_metadata(payload, document["data_version"], document["generated_at"])
        seen.add(key)

    _json_value(document, "快照文档")
    return document
