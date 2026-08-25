"""Strict, aggregate-only contract for analytics query results.

The contract is intentionally independent from Flask, DeepSeek and database
repositories.  It gives later Safe Evidence code one validated, provenance-
carrying result shape without exposing patient-level or physical fields.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .query_plan_contract import (
    FILTER_FIELDS,
    MAX_DIMENSIONS,
    MAX_FILTERS,
    MAX_FILTER_VALUE_LENGTH,
    MAX_FILTER_VALUES,
    MAX_LIMIT,
    MAX_MEASURES,
    MAX_SORT,
    PLAN_FIELDS,
    QUERY_ANALYTICS_VERSION,
    SORT_FIELDS,
)


QUERY_RESULT_VERSION = "query_result-v1"
QUERY_RESULT_CONTRACT_VERSION = QUERY_RESULT_VERSION

SUPPORTED_RESULT_DIMENSIONS = frozenset(
    {
        "hospital",
        "diagnosis",
        "age_group",
        "gender",
        "severity",
        "payment",
        "admission_type",
    }
)
SUPPORTED_RESULT_MEASURES = frozenset(
    {
        "case_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
        "surgical_rate",
        "severe_rate",
    }
)

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_PATIENT_LEVEL_FIELD_PATTERN = re.compile(
    r"(?:^|_)(?:patient|member|mrn|ssn|encounter)(?:$|_)",
    re.IGNORECASE,
)

_FILTER_RESULT_FIELDS = frozenset(
    {"dimension", "operator", "requested", "resolved", "resolution"}
)
_PROVENANCE_FIELDS = frozenset(
    {"batch_id", "data_version", "formula_version", "registry_version"}
)
_METADATA_FIELDS = frozenset({"source", "generated_at", "privacy_boundary"})
_RESULT_FIELDS = frozenset(
    {
        "query_id",
        "query_plan",
        "dimensions",
        "measures",
        "filters",
        "rows",
        "row_count",
        "truncated",
        "provenance",
        "metadata",
    }
)


class QueryResultContractError(ValueError):
    """Raised when a QueryResult v1 document is not safe or complete."""


QueryResultValidationError = QueryResultContractError


def _fail(message: str) -> None:
    raise QueryResultContractError(message)


def _as_document(value: object) -> object:
    to_document = getattr(value, "to_document", None)
    if callable(to_document):
        return to_document()
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    value = _as_document(value)
    if not isinstance(value, Mapping):
        _fail(f"{field} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], field: str
) -> None:
    if set(value) != set(expected):
        unknown = set(value) - set(expected)
        if unknown:
            _fail(f"{field} has unknown fields: {sorted(unknown)[0]}")
        missing = set(expected) - set(value)
        _fail(f"{field} is missing required field: {sorted(missing)[0]}")


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    if value != value.strip() or len(value) > maximum:
        _fail(f"{field} is invalid")
    if _CONTROL_CHARACTER_PATTERN.search(value):
        _fail(f"{field} contains control characters")
    return value


def _identifier(value: object, field: str) -> str:
    result = _text(value, field, maximum=64)
    if _IDENTIFIER_PATTERN.fullmatch(result) is None:
        _fail(f"{field} must be a canonical semantic identifier")
    return result


def _identifier_array(
    value: object,
    field: str,
    *,
    allowed: frozenset[str],
    maximum: int,
    minimum: int = 0,
) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail(f"{field} must be an array")
    if not minimum <= len(value) <= maximum:
        _fail(f"{field} has an invalid item count")

    result: list[str] = []
    for index, item in enumerate(value):
        identifier = _identifier(item, f"{field}[{index}]")
        if identifier not in allowed:
            _fail(f"unknown {field[:-1]}: {identifier}")
        result.append(identifier)
    if len(set(result)) != len(result):
        _fail(f"{field} must not contain duplicates")
    return tuple(result)


def _filter_value(
    value: object,
    field: str,
    operator: str,
) -> str | tuple[str, ...]:
    if operator == "eq":
        return _text(value, field, maximum=MAX_FILTER_VALUE_LENGTH)
    if operator != "in":
        _fail(f"{field}.operator is invalid")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail(f"{field} must be an array for the in operator")
    if not 1 <= len(value) <= MAX_FILTER_VALUES:
        _fail(f"{field} has an invalid item count")
    result = tuple(
        _text(item, f"{field}[{index}]", maximum=MAX_FILTER_VALUE_LENGTH)
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        _fail(f"{field} must not contain duplicates")
    return result


def _value_document(value: str | tuple[str, ...]) -> str | list[str]:
    return list(value) if isinstance(value, tuple) else value


def _normalize_query_plan(value: object) -> dict[str, object]:
    plan = _mapping(value, "query_plan")
    _exact_fields(plan, PLAN_FIELDS, "query_plan")
    if plan["version"] != QUERY_ANALYTICS_VERSION:
        _fail("query_plan has an unsupported version")

    dimensions = _identifier_array(
        plan["dimensions"],
        "query_plan.dimensions",
        allowed=SUPPORTED_RESULT_DIMENSIONS,
        maximum=MAX_DIMENSIONS,
    )
    measures = _identifier_array(
        plan["measures"],
        "query_plan.measures",
        allowed=SUPPORTED_RESULT_MEASURES,
        maximum=MAX_MEASURES,
        minimum=1,
    )

    raw_filters = plan["filters"]
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, (str, bytes)):
        _fail("query_plan.filters must be an array")
    if len(raw_filters) > MAX_FILTERS:
        _fail("query_plan.filters has too many items")
    filters: list[dict[str, object]] = []
    for index, raw_filter in enumerate(raw_filters):
        field = f"query_plan.filters[{index}]"
        item = _mapping(raw_filter, field)
        _exact_fields(item, FILTER_FIELDS, field)
        dimension = _identifier(item["dimension"], f"{field}.dimension")
        if dimension not in SUPPORTED_RESULT_DIMENSIONS:
            _fail(f"unknown filter dimension: {dimension}")
        operator = _text(item["operator"], f"{field}.operator", maximum=8)
        if operator not in {"eq", "in"}:
            _fail(f"{field}.operator is invalid")
        normalized_value = _filter_value(item["value"], field, operator)
        filters.append(
            {
                "dimension": dimension,
                "operator": operator,
                "value": _value_document(normalized_value),
            }
        )

    raw_sort = plan["sort"]
    if not isinstance(raw_sort, Sequence) or isinstance(raw_sort, (str, bytes)):
        _fail("query_plan.sort must be an array")
    if len(raw_sort) > MAX_SORT:
        _fail("query_plan.sort has too many items")
    selected = set(dimensions) | set(measures)
    sort: list[dict[str, str]] = []
    seen_sort: set[str] = set()
    for index, raw_item in enumerate(raw_sort):
        field = f"query_plan.sort[{index}]"
        item = _mapping(raw_item, field)
        _exact_fields(item, SORT_FIELDS, field)
        by = _identifier(item["by"], f"{field}.by")
        if by not in selected:
            _fail(f"{field}.by must reference a selected field")
        direction = _text(item["direction"], f"{field}.direction", maximum=4)
        if direction not in {"asc", "desc"}:
            _fail(f"{field}.direction is invalid")
        if by in seen_sort:
            _fail(f"{field}.by must not be repeated")
        seen_sort.add(by)
        sort.append({"by": by, "direction": direction})

    limit = plan["limit"]
    if isinstance(limit, bool) or not isinstance(limit, int):
        _fail("query_plan.limit must be an integer")
    if not 1 <= limit <= MAX_LIMIT:
        _fail("query_plan.limit is outside the allowed range")

    return {
        "version": QUERY_ANALYTICS_VERSION,
        "dimensions": list(dimensions),
        "measures": list(measures),
        "filters": filters,
        "sort": sort,
        "limit": limit,
    }


def _normalize_result_filter(
    value: object, field: str
) -> dict[str, object]:
    item = _mapping(value, field)
    keys = set(item)
    if keys == set(FILTER_FIELDS):
        dimension = _identifier(item["dimension"], f"{field}.dimension")
        operator = _text(item["operator"], f"{field}.operator", maximum=8)
        normalized = _filter_value(item["value"], field, operator)
        requested = normalized
        resolved = normalized
        resolution = "exact"
    elif keys == set(_FILTER_RESULT_FIELDS):
        dimension = _identifier(item["dimension"], f"{field}.dimension")
        operator = _text(item["operator"], f"{field}.operator", maximum=8)
        requested = _filter_value(item["requested"], field + ".requested", operator)
        resolved = _filter_value(item["resolved"], field + ".resolved", operator)
        resolution = _text(item["resolution"], f"{field}.resolution", maximum=16)
        if resolution not in {"exact", "coarsened"}:
            _fail(f"{field}.resolution is invalid")
        if resolution == "exact" and requested != resolved:
            _fail(f"{field}.exact resolution must preserve requested value")
        if resolution == "coarsened" and dimension != "age_group":
            _fail(f"{field}.coarsened resolution is only valid for age_group")
    else:
        _fail(f"{field} has an invalid filter shape")

    if dimension not in SUPPORTED_RESULT_DIMENSIONS:
        _fail(f"unknown filter dimension: {dimension}")
    return {
        "dimension": dimension,
        "operator": operator,
        "requested": _value_document(requested),
        "resolved": _value_document(resolved),
        "resolution": resolution,
    }


def _normalize_row(
    value: object,
    field: str,
    dimensions: tuple[str, ...],
    measures: tuple[str, ...],
) -> dict[str, Any]:
    row = _mapping(value, field)
    expected = set(dimensions) | set(measures)
    unknown = set(row) - expected
    if unknown:
        unknown_field = sorted(unknown)[0]
        if _PATIENT_LEVEL_FIELD_PATTERN.search(unknown_field):
            _fail(f"{field} contains forbidden patient-level field: {unknown_field}")
        _fail(f"{field} contains unknown field: {unknown_field}")
    missing = expected - set(row)
    if missing:
        _fail(f"{field} is missing field: {sorted(missing)[0]}")

    result: dict[str, Any] = {}
    for dimension in dimensions:
        dimension_value = row[dimension]
        if not isinstance(dimension_value, str) or not dimension_value.strip():
            _fail(f"{field}.{dimension} must be a non-empty string")
        if _CONTROL_CHARACTER_PATTERN.search(dimension_value):
            _fail(f"{field}.{dimension} contains control characters")
        result[dimension] = dimension_value
    for measure in measures:
        measure_value = row[measure]
        if measure_value is not None and (
            isinstance(measure_value, bool)
            or not isinstance(measure_value, (Decimal, int, float))
        ):
            _fail(f"{field}.{measure} must be numeric or null")
        if isinstance(measure_value, float) and not math.isfinite(measure_value):
            _fail(f"{field}.{measure} must be finite")
        if isinstance(measure_value, Decimal) and not measure_value.is_finite():
            _fail(f"{field}.{measure} must be finite")
        result[measure] = measure_value
    return result


def _normalize_result_document(document: object) -> dict[str, object]:
    result = _mapping(document, "query result")
    _exact_fields(result, _RESULT_FIELDS, "query result")
    query_id = _text(result["query_id"], "query_id", maximum=128)
    query_plan = _normalize_query_plan(result["query_plan"])

    dimensions = _identifier_array(
        result["dimensions"],
        "dimensions",
        allowed=SUPPORTED_RESULT_DIMENSIONS,
        maximum=MAX_DIMENSIONS,
    )
    measures = _identifier_array(
        result["measures"],
        "measures",
        allowed=SUPPORTED_RESULT_MEASURES,
        maximum=MAX_MEASURES,
        minimum=1,
    )
    if dimensions != tuple(query_plan["dimensions"]):
        _fail("dimensions must match query_plan.dimensions")
    if measures != tuple(query_plan["measures"]):
        _fail("measures must match query_plan.measures")

    raw_filters = result["filters"]
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, (str, bytes)):
        _fail("filters must be an array")
    if len(raw_filters) > MAX_FILTERS:
        _fail("filters has too many items")
    filters = tuple(
        _normalize_result_filter(item, f"filters[{index}]")
        for index, item in enumerate(raw_filters)
    )
    plan_filters = query_plan["filters"]
    if len(filters) != len(plan_filters):
        _fail("filters must match query_plan.filters")
    for index, (filter_item, plan_item) in enumerate(zip(filters, plan_filters)):
        plan_value = plan_item["value"]
        requested = filter_item["requested"]
        if requested != plan_value:
            _fail(f"filters[{index}] does not match query_plan.filters[{index}]")

    raw_rows = result["rows"]
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        _fail("rows must be an array")
    rows = tuple(
        _normalize_row(item, f"rows[{index}]", dimensions, measures)
        for index, item in enumerate(raw_rows)
    )

    row_count = result["row_count"]
    if isinstance(row_count, bool) or not isinstance(row_count, int):
        _fail("row_count must be an integer")
    if row_count < 0 or row_count != len(rows):
        _fail("row_count must equal the number of returned rows")
    if row_count > int(query_plan["limit"]):
        _fail("row_count exceeds query_plan.limit")

    truncated = result["truncated"]
    if not isinstance(truncated, bool):
        _fail("truncated must be a boolean")

    provenance = _mapping(result["provenance"], "provenance")
    _exact_fields(provenance, _PROVENANCE_FIELDS, "provenance")
    normalized_provenance = {
        field: _text(provenance[field], f"provenance.{field}", maximum=256)
        for field in _PROVENANCE_FIELDS
    }

    metadata = _mapping(result["metadata"], "metadata")
    _exact_fields(metadata, _METADATA_FIELDS, "metadata")
    normalized_metadata = {
        field: _text(metadata[field], f"metadata.{field}", maximum=256)
        for field in _METADATA_FIELDS
    }

    return {
        "query_id": query_id,
        "query_plan": query_plan,
        "dimensions": dimensions,
        "measures": measures,
        "filters": filters,
        "rows": rows,
        "row_count": row_count,
        "truncated": truncated,
        "provenance": normalized_provenance,
        "metadata": normalized_metadata,
    }


@dataclass(frozen=True, slots=True)
class QueryResultContract:
    """Validated QueryResult v1 value object for later evidence conversion."""

    query_id: str
    query_plan: dict[str, object]
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    filters: tuple[dict[str, object], ...]
    rows: tuple[dict[str, Any], ...]
    row_count: int
    truncated: bool
    provenance: dict[str, str]
    metadata: dict[str, str]

    @property
    def batch_id(self) -> str:
        return self.provenance["batch_id"]

    @property
    def data_version(self) -> str:
        return self.provenance["data_version"]

    @property
    def formula_version(self) -> str:
        return self.provenance["formula_version"]

    @property
    def registry_version(self) -> str:
        return self.provenance["registry_version"]

    def __post_init__(self) -> None:
        normalized = _normalize_result_document(
            {
                "query_id": self.query_id,
                "query_plan": self.query_plan,
                "dimensions": self.dimensions,
                "measures": self.measures,
                "filters": self.filters,
                "rows": self.rows,
                "row_count": self.row_count,
                "truncated": self.truncated,
                "provenance": self.provenance,
                "metadata": self.metadata,
            }
        )
        for field, value in normalized.items():
            object.__setattr__(self, field, value)

    @classmethod
    def from_document(cls, document: object) -> "QueryResultContract":
        return validate_query_result(document)

    def to_document(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "query_plan": dict(self.query_plan),
            "dimensions": list(self.dimensions),
            "measures": list(self.measures),
            "filters": [dict(item) for item in self.filters],
            "rows": [dict(item) for item in self.rows],
            "row_count": self.row_count,
            "truncated": self.truncated,
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }


def validate_query_result(document: object) -> QueryResultContract:
    """Validate and normalize a QueryResult v1 document."""

    if isinstance(document, QueryResultContract):
        return document
    normalized = _normalize_result_document(document)
    return QueryResultContract(
        query_id=normalized["query_id"],
        query_plan=normalized["query_plan"],
        dimensions=normalized["dimensions"],
        measures=normalized["measures"],
        filters=normalized["filters"],
        rows=normalized["rows"],
        row_count=normalized["row_count"],
        truncated=normalized["truncated"],
        provenance=normalized["provenance"],
        metadata=normalized["metadata"],
    )


def _semantic_enum(values: frozenset[str]) -> list[str]:
    return sorted(values)


_QUERY_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "dimensions", "measures", "filters", "sort", "limit"],
    "properties": {
        "version": {"const": QUERY_ANALYTICS_VERSION},
        "dimensions": {
            "type": "array",
            "maxItems": MAX_DIMENSIONS,
            "uniqueItems": True,
            "items": {"enum": _semantic_enum(SUPPORTED_RESULT_DIMENSIONS)},
        },
        "measures": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_MEASURES,
            "uniqueItems": True,
            "items": {"enum": _semantic_enum(SUPPORTED_RESULT_MEASURES)},
        },
        "filters": {
            "type": "array",
            "maxItems": MAX_FILTERS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "operator", "value"],
                "properties": {
                    "dimension": {"enum": _semantic_enum(SUPPORTED_RESULT_DIMENSIONS)},
                    "operator": {"enum": ["eq", "in"]},
                    "value": {
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": MAX_FILTER_VALUES,
                                "uniqueItems": True,
                                "items": {"type": "string", "minLength": 1},
                            },
                        ]
                    },
                },
            },
        },
        "sort": {
            "type": "array",
            "maxItems": MAX_SORT,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["by", "direction"],
                "properties": {
                    "by": {
                        "enum": sorted(
                            SUPPORTED_RESULT_DIMENSIONS | SUPPORTED_RESULT_MEASURES
                        )
                    },
                    "direction": {"enum": ["asc", "desc"]},
                },
            },
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
    },
}

_RESULT_FILTER_SCHEMA = {
    "oneOf": [
        _QUERY_PLAN_SCHEMA["properties"]["filters"]["items"],
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "dimension",
                "operator",
                "requested",
                "resolved",
                "resolution",
            ],
            "properties": {
                "dimension": {"enum": _semantic_enum(SUPPORTED_RESULT_DIMENSIONS)},
                "operator": {"enum": ["eq", "in"]},
                "requested": {
                    "oneOf": [
                        {"type": "string", "minLength": 1},
                        {"type": "array", "minItems": 1, "maxItems": MAX_FILTER_VALUES},
                    ]
                },
                "resolved": {
                    "oneOf": [
                        {"type": "string", "minLength": 1},
                        {"type": "array", "minItems": 1, "maxItems": MAX_FILTER_VALUES},
                    ]
                },
                "resolution": {"enum": ["exact", "coarsened"]},
            },
        },
    ]
}

_RESULT_ROW_PROPERTIES = {
    **{
        dimension: {"type": "string"}
        for dimension in SUPPORTED_RESULT_DIMENSIONS
    },
    **{
        measure: {"type": ["number", "null"]}
        for measure in SUPPORTED_RESULT_MEASURES
    },
}

QUERY_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": QUERY_RESULT_VERSION,
    "type": "object",
    "additionalProperties": False,
    "required": sorted(_RESULT_FIELDS),
    "properties": {
        "query_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "query_plan": _QUERY_PLAN_SCHEMA,
        "dimensions": {
            "type": "array",
            "maxItems": MAX_DIMENSIONS,
            "uniqueItems": True,
            "items": {"enum": _semantic_enum(SUPPORTED_RESULT_DIMENSIONS)},
        },
        "measures": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_MEASURES,
            "uniqueItems": True,
            "items": {"enum": _semantic_enum(SUPPORTED_RESULT_MEASURES)},
        },
        "filters": {"type": "array", "maxItems": MAX_FILTERS, "items": _RESULT_FILTER_SCHEMA},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": _RESULT_ROW_PROPERTIES,
            },
        },
        "row_count": {"type": "integer", "minimum": 0, "maximum": MAX_LIMIT},
        "truncated": {"type": "boolean"},
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(_PROVENANCE_FIELDS),
            "properties": {
                field: {"type": "string", "minLength": 1}
                for field in _PROVENANCE_FIELDS
            },
        },
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(_METADATA_FIELDS),
            "properties": {
                field: {"type": "string", "minLength": 1}
                for field in _METADATA_FIELDS
            },
        },
    },
}

QUERY_RESULT_V1_SCHEMA = QUERY_RESULT_SCHEMA


__all__ = [
    "QUERY_RESULT_CONTRACT_VERSION",
    "QUERY_RESULT_SCHEMA",
    "QUERY_RESULT_V1_SCHEMA",
    "QUERY_RESULT_VERSION",
    "QueryResultContract",
    "QueryResultContractError",
    "QueryResultValidationError",
    "SUPPORTED_RESULT_DIMENSIONS",
    "SUPPORTED_RESULT_MEASURES",
    "validate_query_result",
]
