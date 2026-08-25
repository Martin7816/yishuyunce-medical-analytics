"""Contracts for the server-owned analytics semantic registry.

This module contains metadata only.  It does not access a repository, build a
query, or expose a database table to a model.  The query semantic version is
kept separate from the aggregate batch registry version so that the semantic
layer can evolve while remaining compatible with an already active batch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


QUERY_SEMANTIC_REGISTRY_VERSION = "analytics-semantic-v1"
SUPPORTED_DIMENSION_TYPES = frozenset({"enum"})
SUPPORTED_QUERY_OPERATORS = frozenset({"eq", "in"})
SUPPORTED_AGGREGATION_METHODS = frozenset({"sum", "ratio"})

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class SemanticContractError(ValueError):
    """Raised when a semantic registry definition is invalid."""


class UnknownDimensionError(SemanticContractError):
    """Raised when a semantic dimension cannot be resolved."""


class UnknownMeasureError(SemanticContractError):
    """Raised when a semantic measure cannot be resolved."""


def normalize_alias(value: str) -> str:
    """Normalize a human or planner alias without changing its meaning."""

    if not isinstance(value, str):
        raise SemanticContractError("semantic identifiers must be strings")
    normalized = re.sub(r"[\s_-]+", "", value.strip().casefold())
    if not normalized:
        raise SemanticContractError("semantic identifiers must not be blank")
    return normalized


def _validate_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise SemanticContractError(f"{field} must be a lowercase semantic identifier")
    return value


def _validate_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticContractError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise SemanticContractError(f"{field} must not have surrounding whitespace")
    return value


def _validated_text_tuple(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SemanticContractError(f"{field} must be a sequence of strings")
    try:
        result = tuple(_validate_text(value, f"{field}[]") for value in values)
    except TypeError as error:
        raise SemanticContractError(f"{field} must be a sequence of strings") from error
    if not result:
        raise SemanticContractError(f"{field} must not be empty")
    return result


def _deduplicated_normalized(values: Iterable[str], field: str) -> tuple[str, ...]:
    normalized = tuple(normalize_alias(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise SemanticContractError(f"{field} must not contain duplicate aliases")
    return normalized


@dataclass(frozen=True, slots=True)
class DimensionSpec:
    """One user-facing dimension mapped to one server-owned physical field."""

    id: str
    display_name: str
    aliases: tuple[str, ...]
    physical_field: str
    type: str
    allowed_operators: tuple[str, ...]
    privacy_class: str
    capability: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.id, "dimension.id")
        _validate_text(self.display_name, "dimension.display_name")
        _validate_identifier(self.physical_field, "dimension.physical_field")
        if self.type not in SUPPORTED_DIMENSION_TYPES:
            raise SemanticContractError(f"unsupported dimension type: {self.type}")

        aliases = _validated_text_tuple(self.aliases, "dimension.aliases")
        _deduplicated_normalized(aliases, "dimension.aliases")
        object.__setattr__(self, "aliases", aliases)

        operators = _validated_text_tuple(
            self.allowed_operators, "dimension.allowed_operators"
        )
        unknown_operators = set(operators) - SUPPORTED_QUERY_OPERATORS
        if unknown_operators:
            raise SemanticContractError(
                "unsupported dimension operators: "
                + ", ".join(sorted(unknown_operators))
            )
        if len(set(operators)) != len(operators):
            raise SemanticContractError(
                "dimension.allowed_operators must not contain duplicates"
            )
        object.__setattr__(self, "allowed_operators", operators)

        _validate_text(self.privacy_class, "dimension.privacy_class")
        capability = _validated_text_tuple(
            self.capability, "dimension.capability"
        )
        object.__setattr__(self, "capability", capability)

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Plural compatibility view for callers that use capability lists."""

        return self.capability

    def to_document(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "physical_field": self.physical_field,
            "type": self.type,
            "allowed_operators": list(self.allowed_operators),
            "privacy_class": self.privacy_class,
            "capability": list(self.capability),
        }


@dataclass(frozen=True, slots=True)
class MeasureSpec:
    """One safe measure definition over additive aggregate measures."""

    id: str
    display_name: str
    aggregation_method: str
    numerator: str
    denominator: str | None
    validity_rules: tuple[str, ...]
    unit: str
    capability: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.id, "measure.id")
        _validate_text(self.display_name, "measure.display_name")
        if self.aggregation_method not in SUPPORTED_AGGREGATION_METHODS:
            raise SemanticContractError(
                f"unsupported measure aggregation method: {self.aggregation_method}"
            )
        _validate_identifier(self.numerator, "measure.numerator")
        if self.aggregation_method == "ratio":
            if self.denominator is None:
                raise SemanticContractError(
                    "ratio measures require a denominator"
                )
            _validate_identifier(self.denominator, "measure.denominator")
        elif self.denominator is not None:
            raise SemanticContractError(
                "sum measures must not define a denominator"
            )

        validity_rules = _validated_text_tuple(
            self.validity_rules, "measure.validity_rules"
        )
        object.__setattr__(self, "validity_rules", validity_rules)
        _validate_text(self.unit, "measure.unit")
        capability = _validated_text_tuple(
            self.capability, "measure.capability"
        )
        object.__setattr__(self, "capability", capability)

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Plural compatibility view for callers that use capability lists."""

        return self.capability

    def to_document(self) -> dict[str, object | None]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "aggregation_method": self.aggregation_method,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "validity_rules": list(self.validity_rules),
            "unit": self.unit,
            "capability": list(self.capability),
        }


__all__ = [
    "DimensionSpec",
    "MeasureSpec",
    "QUERY_SEMANTIC_REGISTRY_VERSION",
    "SUPPORTED_AGGREGATION_METHODS",
    "SUPPORTED_DIMENSION_TYPES",
    "SUPPORTED_QUERY_OPERATORS",
    "SemanticContractError",
    "UnknownDimensionError",
    "UnknownMeasureError",
    "normalize_alias",
]
