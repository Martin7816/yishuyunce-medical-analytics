"""Server-owned catalogue of safe logical aggregate cube shapes.

The active aggregate fact already stores additive measures at the full
seven-dimensional grain.  A cube shape therefore means a reviewed logical
roll-up over that fact, not another patient-level table and not model-written
SQL.  Keeping the catalogue behind this small interface prevents the planner,
compiler, and repository from maintaining drifting allowlists.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AggregateCubeShape:
    """One reviewed GROUP BY shape over the additive aggregate fact."""

    source_capability: str
    dimensions: frozenset[str]
    purpose: str


_CUBE_SHAPES: tuple[AggregateCubeShape, ...] = (
    AggregateCubeShape("aggregate_overall", frozenset(), "overall metrics"),
    AggregateCubeShape("aggregate_hospital", frozenset({"hospital"}), "hospital ranking"),
    AggregateCubeShape("aggregate_diagnosis", frozenset({"diagnosis"}), "diagnosis ranking"),
    AggregateCubeShape("aggregate_age_group", frozenset({"age_group"}), "age distribution"),
    AggregateCubeShape("aggregate_gender", frozenset({"gender"}), "gender distribution"),
    AggregateCubeShape("aggregate_severity", frozenset({"severity"}), "severity distribution"),
    AggregateCubeShape("aggregate_payment", frozenset({"payment"}), "payment distribution"),
    AggregateCubeShape(
        "aggregate_admission_type",
        frozenset({"admission_type"}),
        "admission type distribution",
    ),
    AggregateCubeShape(
        "aggregate_age_group_diagnosis",
        frozenset({"age_group", "diagnosis"}),
        "diagnosis by age group",
    ),
    AggregateCubeShape(
        "aggregate_gender_diagnosis",
        frozenset({"gender", "diagnosis"}),
        "diagnosis by gender",
    ),
    AggregateCubeShape(
        "aggregate_hospital_severity",
        frozenset({"hospital", "severity"}),
        "hospital by severity",
    ),
    AggregateCubeShape(
        "aggregate_payment_age_group",
        frozenset({"payment", "age_group"}),
        "payment by age group",
    ),
    AggregateCubeShape(
        "aggregate_age_group_gender_diagnosis",
        frozenset({"age_group", "gender", "diagnosis"}),
        "diagnosis by age group and gender",
    ),
    AggregateCubeShape(
        "aggregate_hospital_age_group_diagnosis",
        frozenset({"hospital", "age_group", "diagnosis"}),
        "diagnosis by hospital and age group",
    ),
)

_SHAPES_BY_DIMENSIONS = {shape.dimensions: shape for shape in _CUBE_SHAPES}


def aggregate_cube_shapes() -> tuple[AggregateCubeShape, ...]:
    """Return the immutable reviewed cube catalogue."""

    return _CUBE_SHAPES


def resolve_aggregate_cube_shape(
    dimensions: Iterable[str],
) -> AggregateCubeShape | None:
    """Resolve a dimension set without accepting aliases or arbitrary fields."""

    try:
        key = frozenset(dimensions)
    except TypeError:
        return None
    return _SHAPES_BY_DIMENSIONS.get(key)


def supports_aggregate_cube_shape(dimensions: Iterable[str]) -> bool:
    """Whether the exact dimension set is a reviewed logical roll-up."""

    return resolve_aggregate_cube_shape(dimensions) is not None


__all__ = [
    "AggregateCubeShape",
    "aggregate_cube_shapes",
    "resolve_aggregate_cube_shape",
    "supports_aggregate_cube_shape",
]
