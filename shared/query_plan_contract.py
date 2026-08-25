"""Strict contract for the model-facing analytics query plan.

The contract is deliberately declarative.  A valid plan contains semantic
dimension and measure IDs only; it never contains SQL, table names, physical
fields, joins, or executable expressions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


QUERY_ANALYTICS_VERSION = "query_analytics-v1"
QUERY_PLAN_VERSION = QUERY_ANALYTICS_VERSION

MAX_DIMENSIONS = 3
MAX_MEASURES = 4
MAX_FILTERS = 5
MAX_SORT = 2
MAX_LIMIT = 50
MAX_FILTER_VALUES = 20
MAX_FILTER_VALUE_LENGTH = 128

PLAN_FIELDS = frozenset(
    {"version", "dimensions", "measures", "filters", "sort", "limit"}
)
FILTER_FIELDS = frozenset({"dimension", "operator", "value"})
SORT_FIELDS = frozenset({"by", "direction"})
FORBIDDEN_FIELDS = frozenset(
    {"sql", "table", "join", "field", "expression", "formula"}
)


# This is intentionally exported as data rather than enforced by a third-party
# JSON Schema package.  The backend validator applies the same rules and adds
# registry-dependent checks such as canonical IDs and allowed operators.
QUERY_ANALYTICS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": QUERY_ANALYTICS_VERSION,
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "dimensions", "measures", "filters", "sort", "limit"],
    "properties": {
        "version": {"const": QUERY_ANALYTICS_VERSION},
        "dimensions": {
            "type": "array",
            "maxItems": MAX_DIMENSIONS,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "pattern": "^[a-z][a-z0-9_]*$",
            },
        },
        "measures": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_MEASURES,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "pattern": "^[a-z][a-z0-9_]*$",
            },
        },
        "filters": {
            "type": "array",
            "maxItems": MAX_FILTERS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "operator", "value"],
                "properties": {
                    "dimension": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": "^[a-z][a-z0-9_]*$",
                    },
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
                        "type": "string",
                        "minLength": 1,
                        "pattern": "^[a-z][a-z0-9_]*$",
                    },
                    "direction": {"enum": ["asc", "desc"]},
                },
            },
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LIMIT,
        },
    },
}

# A descriptive alias for callers that use the shorter name.
QUERY_PLAN_SCHEMA = QUERY_ANALYTICS_SCHEMA


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """A validated semantic filter; ``value`` is scalar for eq and tuple for in."""

    dimension: str
    operator: str
    value: str | tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        value: object = list(self.value) if isinstance(self.value, tuple) else self.value
        return {
            "dimension": self.dimension,
            "operator": self.operator,
            "value": value,
        }


@dataclass(frozen=True, slots=True)
class SortSpec:
    """A validated order over a selected semantic dimension or measure."""

    by: str
    direction: str

    def to_document(self) -> dict[str, str]:
        return {"by": self.by, "direction": self.direction}


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """Immutable, server-validated representation of query_analytics-v1."""

    version: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    filters: tuple[FilterSpec, ...]
    sort: tuple[SortSpec, ...]
    limit: int

    def to_document(self) -> dict[str, object]:
        return {
            "version": self.version,
            "dimensions": list(self.dimensions),
            "measures": list(self.measures),
            "filters": [item.to_document() for item in self.filters],
            "sort": [item.to_document() for item in self.sort],
            "limit": self.limit,
        }


__all__ = [
    "FILTER_FIELDS",
    "FORBIDDEN_FIELDS",
    "FilterSpec",
    "MAX_DIMENSIONS",
    "MAX_FILTERS",
    "MAX_FILTER_VALUE_LENGTH",
    "MAX_FILTER_VALUES",
    "MAX_LIMIT",
    "MAX_MEASURES",
    "MAX_SORT",
    "PLAN_FIELDS",
    "QUERY_ANALYTICS_SCHEMA",
    "QUERY_ANALYTICS_VERSION",
    "QUERY_PLAN_SCHEMA",
    "QUERY_PLAN_VERSION",
    "QueryPlan",
    "SORT_FIELDS",
    "SortSpec",
]
