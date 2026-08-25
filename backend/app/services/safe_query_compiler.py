"""Compile validated semantic plans into a repository-neutral query object.

This module is deliberately limited to semantic IDs and validated values.  It
does not create SQL, expose table names or physical fields, or execute a data
operation.  The aggregate repository can consume ``CompiledAggregateQuery``
in a later phase.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from shared.query_plan_contract import FilterSpec, QueryPlan, SortSpec

from .query_plan_validator import QueryPlanValidationError, QueryPlanValidator
from .semantic_registry import SemanticRegistry, semantic_registry


class SafeQueryCompilerError(QueryPlanValidationError):
    """Raised when a validated plan cannot be safely compiled."""


class UnsupportedCapabilityError(SafeQueryCompilerError):
    """Raised when the aggregate source does not support a plan combination."""


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """A server-owned allowlist entry for one aggregate dimension shape."""

    source_capability: str
    dimensions: frozenset[str]
    measures: frozenset[str]

    def supports(
        self, dimensions: Iterable[str], measures: Iterable[str]
    ) -> bool:
        return self.dimensions == frozenset(dimensions) and frozenset(
            measures
        ).issubset(self.measures)


_SUPPORTED_DIMENSION_SHAPES: tuple[tuple[str, frozenset[str]], ...] = (
    ("aggregate_overall", frozenset()),
    ("aggregate_hospital", frozenset({"hospital"})),
    ("aggregate_diagnosis", frozenset({"diagnosis"})),
    ("aggregate_age_group", frozenset({"age_group"})),
    ("aggregate_gender", frozenset({"gender"})),
    ("aggregate_severity", frozenset({"severity"})),
    ("aggregate_payment", frozenset({"payment"})),
    ("aggregate_admission_type", frozenset({"admission_type"})),
    (
        "aggregate_age_group_diagnosis",
        frozenset({"age_group", "diagnosis"}),
    ),
    (
        "aggregate_hospital_severity",
        frozenset({"hospital", "severity"}),
    ),
    (
        "aggregate_payment_age_group",
        frozenset({"payment", "age_group"}),
    ),
)


def build_capability_specs(
    measure_ids: Iterable[str],
) -> tuple[CapabilitySpec, ...]:
    """Build the immutable aggregate capability allowlist for a registry."""

    supported_measures = frozenset(measure_ids)
    return tuple(
        CapabilitySpec(
            source_capability=source_capability,
            dimensions=dimensions,
            measures=supported_measures,
        )
        for source_capability, dimensions in _SUPPORTED_DIMENSION_SHAPES
    )


CAPABILITY_SPECS = build_capability_specs(semantic_registry.measures)

# The current active aggregate source has a coarser age bucket than a request
# for 80+.  Resolution is represented in the compiled filter, never in a
# physical field or executable expression.
AGE_GRANULARITY_FALLBACKS: Mapping[str, str] = {"80+": "70 or Older"}


SemanticValue = str | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompiledFilter:
    """A semantic filter with explicit requested/resolved granularity."""

    dimension: str
    operator: str
    requested: SemanticValue
    resolved: SemanticValue
    resolution: str

    @property
    def value(self) -> SemanticValue:
        """Return the value that a repository should apply."""

        return self.resolved

    @staticmethod
    def _document_value(value: SemanticValue) -> str | list[str]:
        return list(value) if isinstance(value, tuple) else value

    def to_document(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "operator": self.operator,
            "requested": self._document_value(self.requested),
            "resolved": self._document_value(self.resolved),
            "resolution": self.resolution,
        }


@dataclass(frozen=True, slots=True)
class CompiledAggregateQuery:
    """Repository-neutral output of the safe compiler."""

    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    filters: tuple[CompiledFilter, ...]
    order_by: tuple[SortSpec, ...]
    limit: int
    source_capability: str

    def to_document(self) -> dict[str, object]:
        return {
            "dimensions": list(self.dimensions),
            "measures": list(self.measures),
            "filters": [item.to_document() for item in self.filters],
            "order_by": [item.to_document() for item in self.order_by],
            "limit": self.limit,
            "source_capability": self.source_capability,
        }


class SafeQueryCompiler:
    """Validate, capability-check and compile a semantic query plan."""

    def __init__(
        self,
        registry: SemanticRegistry | None = None,
        capabilities: Iterable[CapabilitySpec] | None = None,
    ) -> None:
        self.registry = registry or semantic_registry
        self.validator = QueryPlanValidator(self.registry)
        self.capabilities = tuple(
            capabilities
            if capabilities is not None
            else build_capability_specs(self.registry.measures)
        )
        self._capabilities_by_dimensions = {
            capability.dimensions: capability for capability in self.capabilities
        }

    def _validate_plan(self, plan: object) -> QueryPlan:
        if isinstance(plan, QueryPlan):
            document: object = plan.to_document()
        elif isinstance(plan, Mapping):
            document = plan
        else:
            raise SafeQueryCompilerError(
                "query plan must be a validated QueryPlan or mapping"
            )

        try:
            return self.validator.validate(document)
        except QueryPlanValidationError as error:
            raise SafeQueryCompilerError(str(error)) from error

    def _validate_registry_capabilities(self, plan: QueryPlan) -> None:
        for dimension_id in plan.dimensions:
            try:
                dimension = self.registry.get_dimension(dimension_id)
            except (KeyError, ValueError) as error:
                raise SafeQueryCompilerError(
                    f"unknown dimension: {dimension_id}"
                ) from error
            if "group_by" not in dimension.capabilities:
                raise UnsupportedCapabilityError(
                    f"dimension is not groupable: {dimension_id}"
                )

        for measure_id in plan.measures:
            try:
                measure = self.registry.validate_measure(measure_id)
            except (KeyError, ValueError) as error:
                raise SafeQueryCompilerError(
                    f"unknown measure: {measure_id}"
                ) from error
            if "select" not in measure.capabilities:
                raise UnsupportedCapabilityError(
                    f"measure is not selectable: {measure_id}"
                )

        for filter_spec in plan.filters:
            dimension = self.registry.get_dimension(filter_spec.dimension)
            if "filter" not in dimension.capabilities:
                raise UnsupportedCapabilityError(
                    f"dimension is not filterable: {filter_spec.dimension}"
                )

        selected_dimensions = set(plan.dimensions)
        selected_measures = set(plan.measures)
        for sort_spec in plan.sort:
            if sort_spec.by in selected_dimensions:
                dimension = self.registry.get_dimension(sort_spec.by)
                if "sort" not in dimension.capabilities:
                    raise UnsupportedCapabilityError(
                        f"dimension is not sortable: {sort_spec.by}"
                    )
            elif sort_spec.by in selected_measures:
                measure = self.registry.validate_measure(sort_spec.by)
                if "sort" not in measure.capabilities:
                    raise UnsupportedCapabilityError(
                        f"measure is not sortable: {sort_spec.by}"
                    )

    def _resolve_age_value(self, value: str) -> str:
        for requested, resolved in AGE_GRANULARITY_FALLBACKS.items():
            if value.casefold() == requested.casefold():
                return resolved
        return value

    def _compile_filter(self, filter_spec: FilterSpec) -> CompiledFilter:
        requested = filter_spec.value
        if isinstance(requested, tuple):
            resolved_values = tuple(
                self._resolve_age_value(value)
                if filter_spec.dimension == "age_group"
                else value
                for value in requested
            )
            if len(set(resolved_values)) != len(resolved_values):
                raise SafeQueryCompilerError(
                    "age granularity fallback creates duplicate resolved values"
                )
            resolved: SemanticValue = resolved_values
        else:
            resolved = (
                self._resolve_age_value(requested)
                if filter_spec.dimension == "age_group"
                else requested
            )

        resolution = "coarsened" if resolved != requested else "exact"
        return CompiledFilter(
            dimension=filter_spec.dimension,
            operator=filter_spec.operator,
            requested=requested,
            resolved=resolved,
            resolution=resolution,
        )

    def compile(
        self, plan: QueryPlan | Mapping[str, Any]
    ) -> CompiledAggregateQuery:
        """Compile a plan without touching a repository or producing SQL."""

        validated_plan = self._validate_plan(plan)
        self._validate_registry_capabilities(validated_plan)

        capability = self._capabilities_by_dimensions.get(
            frozenset(validated_plan.dimensions)
        )
        if capability is None or not capability.supports(
            validated_plan.dimensions, validated_plan.measures
        ):
            dimensions = ", ".join(validated_plan.dimensions) or "(none)"
            raise UnsupportedCapabilityError(
                f"unsupported aggregate capability for dimensions: {dimensions}"
            )

        return CompiledAggregateQuery(
            dimensions=validated_plan.dimensions,
            measures=validated_plan.measures,
            filters=tuple(
                self._compile_filter(item) for item in validated_plan.filters
            ),
            order_by=validated_plan.sort,
            limit=validated_plan.limit,
            source_capability=capability.source_capability,
        )


def compile_query_plan(
    plan: QueryPlan | Mapping[str, Any],
    registry: SemanticRegistry | None = None,
) -> CompiledAggregateQuery:
    """Compile a plan with the default server-owned semantic registry."""

    return SafeQueryCompiler(registry).compile(plan)


__all__ = [
    "AGE_GRANULARITY_FALLBACKS",
    "CAPABILITY_SPECS",
    "CapabilitySpec",
    "CompiledAggregateQuery",
    "CompiledFilter",
    "SafeQueryCompiler",
    "SafeQueryCompilerError",
    "UnsupportedCapabilityError",
    "build_capability_specs",
    "compile_query_plan",
]
