"""Read-only adapter for safe semantic queries over the active aggregate fact.

The adapter accepts only ``CompiledAggregateQuery``.  SQL is assembled from
server-owned semantic and measure allowlists; caller values are always bound
parameters.  The data query itself reads one table only:
``analytics_aggregate_fact``.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from shared.aggregate_contract import (
    AGGREGATE_FACT_TABLE,
    AGGREGATE_GRAIN,
    AGGREGATE_MEASURES,
)
from shared.query_plan_contract import (
    MAX_DIMENSIONS,
    MAX_FILTERS,
    MAX_FILTER_VALUE_LENGTH,
    MAX_FILTER_VALUES,
    MAX_LIMIT,
    MAX_MEASURES,
    MAX_SORT,
    SortSpec,
)
from shared.disease_rules import NON_DISEASE_DIAGNOSIS_CODES

from ..errors import (
    AppError,
    DatabaseUnavailableError,
    InvalidServiceResultError,
    ResultNotReadyError,
    ServerMisconfiguredError,
)
from ..services.safe_query_compiler import (
    CompiledAggregateQuery,
    CompiledFilter,
    build_capability_specs,
)
from ..services.semantic_registry import SemanticRegistry, semantic_registry
from .aggregate import MySQLAggregateFactRepository
from shared.query_result_contract import QueryResultContract


class AggregateQueryValidationError(ValueError):
    """Raised when a compiled query fails repository-side defense-in-depth."""


_SEMANTIC_TO_PHYSICAL_FIELD = {
    "hospital": "facility_id",
    "diagnosis": "diagnosis_code",
    "age_group": "age",
    "gender": "gender",
    "severity": "severity",
    "payment": "payment",
    "admission_type": "admission",
}
_ALLOWED_PHYSICAL_FIELDS = frozenset(AGGREGATE_GRAIN)
_ALLOWED_MEASURE_FIELDS = frozenset(AGGREGATE_MEASURES)
_MAX_RESULT_ROWS = MAX_LIMIT

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_SQL_KEYWORD_PATTERN = re.compile(
    r"\b(select|insert|update|delete|drop|alter|truncate|union)\b",
    re.IGNORECASE,
)
_BOOLEAN_INJECTION_PATTERN = re.compile(
    r"(?:\b(?:or|and)\b\s*['\"\d]|['\"]\s*(?:or|and)\b)",
    re.IGNORECASE,
)


def _quote_identifier(identifier: str) -> str:
    """Quote an identifier that has already passed a server allowlist."""

    return f"`{identifier}`"


def _safe_filter_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AggregateQueryValidationError(f"{field} must be a non-empty string")
    if value != value.strip() or len(value) > MAX_FILTER_VALUE_LENGTH:
        raise AggregateQueryValidationError(f"{field} is invalid")
    if _CONTROL_CHARACTER_PATTERN.search(value):
        raise AggregateQueryValidationError(f"{field} contains control characters")
    if any(marker in value for marker in (";", "--", "/*", "*/", "'", '"')):
        raise AggregateQueryValidationError(f"{field} contains unsafe query syntax")
    if _SQL_KEYWORD_PATTERN.search(value) or _BOOLEAN_INJECTION_PATTERN.search(value):
        raise AggregateQueryValidationError(f"{field} contains unsafe query syntax")
    return value


class MySQLAggregateQueryRepository:
    """Execute a compiled query against the currently active aggregate batch."""

    def __init__(
        self,
        config: Mapping[str, Any],
        active_batch_repository: Any | None = None,
        connection_factory: Callable[[], Any] | None = None,
        registry: SemanticRegistry | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or semantic_registry
        self._fact_repository = MySQLAggregateFactRepository(config)
        self._active_batch_repository = (
            active_batch_repository
            if active_batch_repository is not None
            else self._fact_repository
        )
        self._connection_factory = connection_factory
        self._capabilities = {
            capability.dimensions: capability
            for capability in build_capability_specs(self.registry.measures)
        }

    def _connect(self) -> Any:
        if self._connection_factory is not None:
            return self._connection_factory()
        return self._fact_repository._connect()

    def _active_batch(self) -> dict[str, str]:
        batch = self._active_batch_repository.fetch_active_batch()
        if not isinstance(batch, Mapping) or batch.get("status") != "ACTIVE":
            raise ResultNotReadyError("active aggregate batch")

        required = ("batch_id", "data_version", "formula_version", "registry_version")
        result: dict[str, str] = {}
        for field in required:
            value = batch.get(field)
            if not isinstance(value, str) or not value.strip():
                raise InvalidServiceResultError()
            result[field] = value
        return result

    def _dimension_field(self, dimension_id: str) -> str:
        if dimension_id not in _SEMANTIC_TO_PHYSICAL_FIELD:
            raise AggregateQueryValidationError(
                f"unknown aggregate dimension: {dimension_id}"
            )
        dimension = self.registry.get_dimension(dimension_id)
        field = _SEMANTIC_TO_PHYSICAL_FIELD[dimension_id]
        if (
            dimension.physical_field != field
            or field not in _ALLOWED_PHYSICAL_FIELDS
        ):
            raise AggregateQueryValidationError(
                f"dimension is not supported by aggregate fact: {dimension_id}"
            )
        return field

    def _measure_expression(self, measure_id: str) -> str:
        measure = self.registry.validate_measure(measure_id)
        numerator = measure.numerator
        if numerator not in _ALLOWED_MEASURE_FIELDS:
            raise AggregateQueryValidationError(
                f"measure numerator is not supported: {measure_id}"
            )

        numerator_sql = f"f.{_quote_identifier(numerator)}"
        if measure.aggregation_method == "sum":
            return f"SUM({numerator_sql})"

        denominator = measure.denominator
        if denominator is None or denominator not in _ALLOWED_MEASURE_FIELDS:
            raise AggregateQueryValidationError(
                f"measure denominator is not supported: {measure_id}"
            )
        denominator_sql = f"f.{_quote_identifier(denominator)}"
        return f"SUM({numerator_sql}) / NULLIF(SUM({denominator_sql}), 0)"

    def _validate_filter(self, filter_spec: CompiledFilter) -> None:
        if not isinstance(filter_spec, CompiledFilter):
            raise AggregateQueryValidationError("filters must contain CompiledFilter")
        self._dimension_field(filter_spec.dimension)
        if filter_spec.operator not in {"eq", "in"}:
            raise AggregateQueryValidationError(
                f"invalid filter operator: {filter_spec.operator}"
            )
        if filter_spec.resolution not in {"exact", "coarsened"}:
            raise AggregateQueryValidationError("invalid filter resolution")
        if filter_spec.resolution == "exact" and (
            filter_spec.requested != filter_spec.resolved
        ):
            raise AggregateQueryValidationError(
                "exact filter resolution must preserve the requested value"
            )
        if filter_spec.resolution == "coarsened" and filter_spec.dimension != "age_group":
            raise AggregateQueryValidationError(
                "only age_group supports coarsened filter resolution"
            )

        if filter_spec.operator == "eq":
            if not isinstance(filter_spec.requested, str) or not isinstance(
                filter_spec.resolved, str
            ):
                raise AggregateQueryValidationError(
                    "eq filter values must be strings"
                )
            _safe_filter_value(filter_spec.requested, "filter.requested")
            _safe_filter_value(filter_spec.resolved, "filter.resolved")
            return

        if not isinstance(filter_spec.requested, tuple) or not isinstance(
            filter_spec.resolved, tuple
        ):
            raise AggregateQueryValidationError("in filter values must be tuples")
        if not 1 <= len(filter_spec.requested) <= MAX_FILTER_VALUES:
            raise AggregateQueryValidationError("in filter has too many values")
        if len(filter_spec.requested) != len(filter_spec.resolved):
            raise AggregateQueryValidationError(
                "in filter requested/resolved values must have equal length"
            )
        if len(set(filter_spec.requested)) != len(filter_spec.requested):
            raise AggregateQueryValidationError("in filter values must be unique")
        if len(set(filter_spec.resolved)) != len(filter_spec.resolved):
            raise AggregateQueryValidationError("resolved filter values must be unique")
        for index, value in enumerate(filter_spec.requested):
            _safe_filter_value(value, f"filter.requested[{index}]")
        for index, value in enumerate(filter_spec.resolved):
            _safe_filter_value(value, f"filter.resolved[{index}]")

    def _validate_query(self, query: CompiledAggregateQuery) -> None:
        if not isinstance(query, CompiledAggregateQuery):
            raise AggregateQueryValidationError(
                "aggregate query must be CompiledAggregateQuery"
            )
        if not isinstance(query.dimensions, tuple) or not 0 <= len(
            query.dimensions
        ) <= MAX_DIMENSIONS:
            raise AggregateQueryValidationError("invalid aggregate dimensions")
        if len(set(query.dimensions)) != len(query.dimensions):
            raise AggregateQueryValidationError("aggregate dimensions must be unique")
        if not isinstance(query.measures, tuple) or not 1 <= len(
            query.measures
        ) <= MAX_MEASURES:
            raise AggregateQueryValidationError("invalid aggregate measures")
        if len(set(query.measures)) != len(query.measures):
            raise AggregateQueryValidationError("aggregate measures must be unique")
        if not isinstance(query.filters, tuple) or len(query.filters) > MAX_FILTERS:
            raise AggregateQueryValidationError("invalid aggregate filters")
        if not isinstance(query.order_by, tuple) or len(query.order_by) > MAX_SORT:
            raise AggregateQueryValidationError("invalid aggregate order_by")
        if isinstance(query.limit, bool) or not isinstance(query.limit, int):
            raise AggregateQueryValidationError("aggregate limit must be an integer")
        if not 1 <= query.limit <= _MAX_RESULT_ROWS:
            raise AggregateQueryValidationError("aggregate limit exceeds the row limit")

        for dimension_id in query.dimensions:
            self._dimension_field(dimension_id)
        for measure_id in query.measures:
            self._measure_expression(measure_id)
        for filter_spec in query.filters:
            self._validate_filter(filter_spec)

        selected = set(query.dimensions) | set(query.measures)
        for order_by in query.order_by:
            if not isinstance(order_by, SortSpec):
                raise AggregateQueryValidationError("order_by must contain SortSpec")
            if order_by.by not in selected:
                raise AggregateQueryValidationError(
                    "order_by must reference a selected semantic field"
                )
            if order_by.direction not in {"asc", "desc"}:
                raise AggregateQueryValidationError("invalid order direction")

        capability = self._capabilities.get(frozenset(query.dimensions))
        if (
            capability is None
            or not capability.supports(query.dimensions, query.measures)
            or query.source_capability != capability.source_capability
        ):
            raise AggregateQueryValidationError(
                "aggregate query capability does not match the active source"
            )

    def _build_sql(
        self, query: CompiledAggregateQuery, batch_id: str
    ) -> tuple[str, tuple[Any, ...]]:
        selected: list[str] = []
        for dimension_id in query.dimensions:
            field = self._dimension_field(dimension_id)
            selected.append(
                f"f.{_quote_identifier(field)} AS {_quote_identifier(dimension_id)}"
            )
        for measure_id in query.measures:
            selected.append(
                f"{self._measure_expression(measure_id)} AS {_quote_identifier(measure_id)}"
            )

        query_sql = (
            f"SELECT {', '.join(selected)} "
            f"FROM {_quote_identifier(AGGREGATE_FACT_TABLE)} AS f "
            "WHERE f.`batch_id` = %s"
        )
        params: list[Any] = [batch_id]

        if "diagnosis" in query.dimensions:
            excluded_codes = tuple(sorted(NON_DISEASE_DIAGNOSIS_CODES))
            if excluded_codes:
                placeholders = ", ".join("%s" for _ in excluded_codes)
                query_sql += (
                    f" AND f.`diagnosis_code` NOT IN ({placeholders})"
                )
                params.extend(excluded_codes)

        for filter_spec in query.filters:
            field = self._dimension_field(filter_spec.dimension)
            field_sql = f"f.{_quote_identifier(field)}"
            if filter_spec.operator == "eq":
                query_sql += f" AND {field_sql} = %s"
                params.append(filter_spec.resolved)
            else:
                placeholders = ", ".join("%s" for _ in filter_spec.resolved)
                query_sql += f" AND {field_sql} IN ({placeholders})"
                params.extend(filter_spec.resolved)

        if query.dimensions:
            query_sql += " GROUP BY " + ", ".join(
                _quote_identifier(dimension_id) for dimension_id in query.dimensions
            )
        if query.order_by:
            query_sql += " ORDER BY " + ", ".join(
                f"{_quote_identifier(item.by)} {item.direction.upper()}"
                for item in query.order_by
            )
        query_sql += " LIMIT %s"
        params.append(query.limit)
        return query_sql, tuple(params)

    @staticmethod
    def _rows(
        fetched: object,
        query: CompiledAggregateQuery,
    ) -> tuple[tuple[dict[str, Any], ...], bool]:
        if not isinstance(fetched, Sequence) or isinstance(fetched, (str, bytes)):
            raise InvalidServiceResultError()
        fetched_rows = list(fetched)
        truncated = len(fetched_rows) > query.limit
        expected = tuple((*query.dimensions, *query.measures))
        expected_keys = set(expected)
        rows: list[dict[str, Any]] = []
        # LIMIT is part of the SQL, and slicing is a second boundary in case a
        # test double or a non-conforming driver returns more rows.
        for raw_row in fetched_rows[: query.limit]:
            if not isinstance(raw_row, Mapping) or set(raw_row) != expected_keys:
                raise InvalidServiceResultError()
            rows.append({key: raw_row[key] for key in expected})
        return tuple(rows), truncated

    @staticmethod
    def _query_plan_document(query: CompiledAggregateQuery) -> dict[str, object]:
        def filter_value(value: str | tuple[str, ...]) -> str | list[str]:
            return list(value) if isinstance(value, tuple) else value

        return {
            "version": "query_analytics-v1",
            "dimensions": list(query.dimensions),
            "measures": list(query.measures),
            "filters": [
                {
                    "dimension": item.dimension,
                    "operator": item.operator,
                    "value": filter_value(item.requested),
                }
                for item in query.filters
            ],
            "sort": [item.to_document() for item in query.order_by],
            "limit": query.limit,
        }

    def execute(self, query: CompiledAggregateQuery) -> QueryResultContract:
        self._validate_query(query)
        batch = self._active_batch()
        query_sql, params = self._build_sql(query, batch["batch_id"])
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query_sql, params)
                rows, truncated = self._rows(cursor.fetchall(), query)
        except (AppError, AggregateQueryValidationError):
            raise
        except Exception as error:
            try:
                import pymysql
            except ImportError:
                raise ServerMisconfiguredError() from error
            if isinstance(error, pymysql.MySQLError):
                raise DatabaseUnavailableError() from error
            raise
        finally:
            connection.close()

        generated_at = datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        return QueryResultContract(
            query_id=uuid.uuid4().hex,
            query_plan=self._query_plan_document(query),
            dimensions=query.dimensions,
            measures=query.measures,
            filters=query.filters,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            provenance={
                "batch_id": batch["batch_id"],
                "data_version": batch["data_version"],
                "formula_version": batch["formula_version"],
                "registry_version": batch["registry_version"],
            },
            metadata={
                "source": "analytics_aggregate_fact",
                "generated_at": generated_at,
                "privacy_boundary": "aggregate_only",
            },
        )

    def query(self, query: CompiledAggregateQuery) -> QueryResultContract:
        """Alias for callers that name repository reads ``query``."""

        return self.execute(query)


class DisabledAggregateQueryRepository:
    """Fail closed when the internal aggregate source is not configured."""

    def execute(self, query: CompiledAggregateQuery) -> QueryResultContract:
        raise ServerMisconfiguredError()

    def query(self, query: CompiledAggregateQuery) -> QueryResultContract:
        raise ServerMisconfiguredError()


def build_aggregate_query_repository(
    config: Mapping[str, Any],
    active_batch_repository: Any | None = None,
) -> MySQLAggregateQueryRepository | DisabledAggregateQueryRepository:
    source = str(config.get("AGGREGATE_DATA_SOURCE") or "").lower()
    if source == "mysql":
        return MySQLAggregateQueryRepository(config, active_batch_repository)
    return DisabledAggregateQueryRepository()


__all__ = [
    "AggregateQueryValidationError",
    "DisabledAggregateQueryRepository",
    "MySQLAggregateQueryRepository",
    "QueryResultContract",
    "build_aggregate_query_repository",
]
