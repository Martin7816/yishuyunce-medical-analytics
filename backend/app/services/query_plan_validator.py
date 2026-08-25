"""Validation for the model-facing query_analytics-v1 plan."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from shared.query_plan_contract import (
    FILTER_FIELDS,
    FORBIDDEN_FIELDS,
    MAX_DIMENSIONS,
    MAX_FILTERS,
    MAX_FILTER_VALUE_LENGTH,
    MAX_FILTER_VALUES,
    MAX_LIMIT,
    MAX_MEASURES,
    MAX_SORT,
    PLAN_FIELDS,
    QUERY_ANALYTICS_VERSION,
    QueryPlan,
    FilterSpec,
    SORT_FIELDS,
    SortSpec,
)

from .semantic_registry import SemanticRegistry, semantic_registry


class QueryPlanValidationError(ValueError):
    """Raised when a query plan violates the frozen contract."""


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_SQL_KEYWORD_PATTERN = re.compile(
    r"\b(select|insert|update|delete|drop|alter|truncate|union)\b",
    re.IGNORECASE,
)
_BOOLEAN_INJECTION_PATTERN = re.compile(
    r"(?:\b(?:or|and)\b\s*['\"\d]|['\"]\s*(?:or|and)\b)",
    re.IGNORECASE,
)


def _fail(message: str) -> None:
    raise QueryPlanValidationError(message)


def _require_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field} must be an object")
    return value


def _require_exact_fields(
    value: Mapping[str, Any], allowed: frozenset[str], field: str
) -> None:
    unknown = set(value) - set(allowed)
    if unknown:
        forbidden = unknown & FORBIDDEN_FIELDS
        if forbidden:
            _fail(f"forbidden query plan field: {sorted(forbidden)[0]}")
        _fail(f"unknown query plan field: {sorted(unknown)[0]}")


def _require_string(value: object, field: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    if value != value.strip():
        _fail(f"{field} must not have surrounding whitespace")
    if max_length is not None and len(value) > max_length:
        _fail(f"{field} is too long")
    if _CONTROL_CHARACTER_PATTERN.search(value):
        _fail(f"{field} contains control characters")
    if any(marker in value for marker in (";", "--", "/*", "*/", "'", '"')):
        _fail(f"{field} contains unsafe query syntax")
    if _SQL_KEYWORD_PATTERN.search(value) or _BOOLEAN_INJECTION_PATTERN.search(value):
        _fail(f"{field} contains unsafe query syntax")
    return value


def _require_canonical_identifier(value: object, field: str) -> str:
    identifier = _require_string(value, field, max_length=64)
    if _IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        _fail(f"{field} must be a canonical semantic identifier")
    return identifier


def _require_string_array(
    value: object,
    field: str,
    *,
    maximum: int,
    minimum: int = 0,
) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail(f"{field} must be an array")
    if not minimum <= len(value) <= maximum:
        _fail(f"{field} must contain between {minimum} and {maximum} items")

    result = tuple(
        _require_canonical_identifier(item, f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        _fail(f"{field} must not contain duplicates")
    return result


class QueryPlanValidator:
    """Validate and canonicalize query_analytics-v1 without executing it."""

    def __init__(self, registry: SemanticRegistry | None = None) -> None:
        self.registry = registry or semantic_registry

    def _dimensions(self, value: object) -> tuple[str, ...]:
        dimensions = _require_string_array(
            value,
            "dimensions",
            maximum=MAX_DIMENSIONS,
        )
        for dimension_id in dimensions:
            if dimension_id not in self.registry.dimensions:
                _fail(f"unknown dimension: {dimension_id}")
        return dimensions

    def _measures(self, value: object) -> tuple[str, ...]:
        measures = _require_string_array(
            value,
            "measures",
            maximum=MAX_MEASURES,
            minimum=1,
        )
        for measure_id in measures:
            if measure_id not in self.registry.measures:
                _fail(f"unknown measure: {measure_id}")
        return measures

    def _filter_value(
        self, value: object, field: str, operator: str
    ) -> str | tuple[str, ...]:
        if operator == "eq":
            return _require_string(value, field, max_length=MAX_FILTER_VALUE_LENGTH)

        if operator != "in":
            _fail(f"invalid filter operator: {operator}")
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            _fail(f"{field} must be an array for the in operator")
        if not 1 <= len(value) <= MAX_FILTER_VALUES:
            _fail(f"{field} must contain between 1 and {MAX_FILTER_VALUES} items")
        normalized = tuple(
            _require_string(
                item,
                f"{field}[{index}]",
                max_length=MAX_FILTER_VALUE_LENGTH,
            )
            for index, item in enumerate(value)
        )
        if len(set(normalized)) != len(normalized):
            _fail(f"{field} must not contain duplicates")
        return normalized

    def _filters(self, value: object) -> tuple[FilterSpec, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            _fail("filters must be an array")
        if len(value) > MAX_FILTERS:
            _fail(f"filters must contain at most {MAX_FILTERS} items")

        filters: list[FilterSpec] = []
        seen: set[tuple[str, str, str]] = set()
        for index, raw_filter in enumerate(value):
            field = f"filters[{index}]"
            document = _require_mapping(raw_filter, field)
            _require_exact_fields(document, FILTER_FIELDS, field)
            if set(document) != set(FILTER_FIELDS):
                _fail(f"{field} must contain exactly dimension, operator and value")

            dimension_id = _require_canonical_identifier(
                document["dimension"], f"{field}.dimension"
            )
            if dimension_id not in self.registry.dimensions:
                _fail(f"unknown dimension: {dimension_id}")
            operator = _require_string(document["operator"], f"{field}.operator")
            dimension = self.registry.get_dimension(dimension_id)
            if operator not in dimension.allowed_operators:
                _fail(f"invalid filter operator: {operator}")
            filter_value = self._filter_value(
                document["value"], f"{field}.value", operator
            )
            value_key = (
                filter_value
                if isinstance(filter_value, str)
                else "|".join(filter_value)
            )
            identity = (dimension_id, operator, value_key)
            if identity in seen:
                _fail(f"{field} duplicates an earlier filter")
            seen.add(identity)
            filters.append(FilterSpec(dimension_id, operator, filter_value))
        return tuple(filters)

    def _sort(
        self, value: object, dimensions: tuple[str, ...], measures: tuple[str, ...]
    ) -> tuple[SortSpec, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            _fail("sort must be an array")
        if len(value) > MAX_SORT:
            _fail(f"sort must contain at most {MAX_SORT} items")

        selected = set(dimensions) | set(measures)
        result: list[SortSpec] = []
        seen: set[str] = set()
        for index, raw_sort in enumerate(value):
            field = f"sort[{index}]"
            document = _require_mapping(raw_sort, field)
            _require_exact_fields(document, SORT_FIELDS, field)
            if set(document) != set(SORT_FIELDS):
                _fail(f"{field} must contain exactly by and direction")
            sort_by = _require_canonical_identifier(document["by"], f"{field}.by")
            if sort_by not in selected:
                _fail(f"{field}.by must reference a selected dimension or measure")
            direction = _require_string(document["direction"], f"{field}.direction")
            if direction not in {"asc", "desc"}:
                _fail(f"invalid sort direction: {direction}")
            if sort_by in seen:
                _fail(f"{field}.by must not be repeated")
            seen.add(sort_by)
            result.append(SortSpec(sort_by, direction))
        return tuple(result)

    def validate(self, document: object) -> QueryPlan:
        plan = _require_mapping(document, "query plan")
        _require_exact_fields(plan, PLAN_FIELDS, "query plan")
        if set(plan) != set(PLAN_FIELDS):
            _fail("query plan must contain exactly the frozen fields")
        if plan["version"] != QUERY_ANALYTICS_VERSION:
            _fail("unsupported query plan version")

        dimensions = self._dimensions(plan["dimensions"])
        measures = self._measures(plan["measures"])
        filters = self._filters(plan["filters"])
        sort = self._sort(plan["sort"], dimensions, measures)

        limit = plan["limit"]
        if isinstance(limit, bool) or not isinstance(limit, int):
            _fail("limit must be an integer")
        if not 1 <= limit <= MAX_LIMIT:
            _fail(f"limit must be between 1 and {MAX_LIMIT}")

        return QueryPlan(
            version=QUERY_ANALYTICS_VERSION,
            dimensions=dimensions,
            measures=measures,
            filters=filters,
            sort=sort,
            limit=limit,
        )


def validate_query_plan(
    document: object, registry: SemanticRegistry | None = None
) -> QueryPlan:
    return QueryPlanValidator(registry).validate(document)


__all__ = ["QueryPlanValidationError", "QueryPlanValidator", "validate_query_plan"]
