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


PAYLOAD_KEYS = frozenset(
    {"title", "description", "options", "filters", "metrics", "sections"}
)
PAYLOAD_REQUIRED_KEYS = frozenset({"title", "description", "metrics", "sections"})
SECTION_TYPES = frozenset({"bar", "pie", "table", "status"})
DOCUMENT_KEYS = frozenset({"data_version", "generated_at", "records", "input"})


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


def _validate_sections(sections: Any) -> None:
    if not isinstance(sections, list):
        _fail("payload.sections 必须是数组")
    for index, section in enumerate(sections):
        field = f"sections[{index}]"
        if not isinstance(section, dict):
            _fail(f"{field} 必须是对象")
        _object_keys(section, {"key", "title", "type", "items"}, field)
        _string(section.get("key"), f"{field}.key")
        _string(section.get("title"), f"{field}.title")
        section_type = section.get("type")
        if section_type not in SECTION_TYPES:
            _fail(f"{field}.type 只能是 bar、pie、table 或 status")
        items = section.get("items")
        if not isinstance(items, list):
            _fail(f"{field}.items 必须是数组")
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
    _json_value(payload, "payload")
    return payload


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
        validate_payload(record.get("payload"))
        seen.add(key)

    _json_value(document, "快照文档")
    return document
