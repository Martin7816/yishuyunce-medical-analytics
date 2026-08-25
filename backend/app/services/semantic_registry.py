"""Server-owned semantic registry for safe analytics planning.

The registry is metadata only.  It does not call DeepSeek, execute SQL, read
the aggregate repository, or expose a database table to a caller.
"""

from __future__ import annotations

from collections.abc import Mapping

from shared.query_semantic_contract import (
    DimensionSpec,
    MeasureSpec,
    QUERY_SEMANTIC_REGISTRY_VERSION,
    UnknownDimensionError,
    UnknownMeasureError,
    normalize_alias,
)


# This is deliberately a different version from shared.aggregate_registry's
# aggregate-registry-v1.  The active aggregate batch remains compatible with
# the low-level physical contract while this user-facing semantic layer grows.
SEMANTIC_REGISTRY_VERSION = QUERY_SEMANTIC_REGISTRY_VERSION

_DIMENSION_CAPABILITIES = ("group_by", "filter", "sort", "top_k")
_MEASURE_CAPABILITIES = ("select", "sort", "compare")


DIMENSION_SPECS: dict[str, DimensionSpec] = {
    "hospital": DimensionSpec(
        id="hospital",
        display_name="医院",
        aliases=("hospital", "hospitals", "facility", "facilities", "医院", "机构"),
        physical_field="facility_id",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="sensitive_category",
        capability=_DIMENSION_CAPABILITIES,
    ),
    "diagnosis": DimensionSpec(
        id="diagnosis",
        display_name="诊断",
        aliases=("diagnosis", "diagnosis_code", "disease", "病种", "疾病", "诊断"),
        physical_field="diagnosis_code",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="sensitive_category",
        capability=_DIMENSION_CAPABILITIES,
    ),
    "age_group": DimensionSpec(
        id="age_group",
        display_name="年龄组",
        aliases=("age_group", "age", "年龄", "年龄组", "年龄段"),
        physical_field="age",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="quasi_identifier",
        capability=_DIMENSION_CAPABILITIES,
    ),
    "gender": DimensionSpec(
        id="gender",
        display_name="性别",
        aliases=("gender", "sex", "性别"),
        physical_field="gender",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="quasi_identifier",
        capability=_DIMENSION_CAPABILITIES,
    ),
    "severity": DimensionSpec(
        id="severity",
        display_name="病情严重程度",
        aliases=("severity", "acuity", "严重程度", "病情严重程度"),
        physical_field="severity",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="quasi_identifier",
        capability=_DIMENSION_CAPABILITIES,
    ),
    "payment": DimensionSpec(
        id="payment",
        display_name="支付方式",
        aliases=("payment", "payer", "payment_type", "支付", "支付方式", "医保"),
        physical_field="payment",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="quasi_identifier",
        capability=_DIMENSION_CAPABILITIES,
    ),
    "admission_type": DimensionSpec(
        id="admission_type",
        display_name="入院方式",
        aliases=(
            "admission_type",
            "admission",
            "入院",
            "入院方式",
            "入院类型",
        ),
        physical_field="admission",
        type="enum",
        allowed_operators=("eq", "in"),
        privacy_class="quasi_identifier",
        capability=_DIMENSION_CAPABILITIES,
    ),
}


MEASURE_SPECS: dict[str, MeasureSpec] = {
    "case_count": MeasureSpec(
        id="case_count",
        display_name="病例量",
        aggregation_method="sum",
        numerator="record_count",
        denominator=None,
        validity_rules=("numerator_positive",),
        unit="条",
        capability=("select", "sort", "rank"),
    ),
    "avg_los": MeasureSpec(
        id="avg_los",
        display_name="平均住院时长",
        aggregation_method="ratio",
        numerator="los_sum",
        denominator="los_valid_count",
        validity_rules=("denominator_positive",),
        unit="天",
        capability=_MEASURE_CAPABILITIES,
    ),
    "avg_charges": MeasureSpec(
        id="avg_charges",
        display_name="平均收费",
        aggregation_method="ratio",
        numerator="charges_sum",
        denominator="charges_valid_count",
        validity_rules=("denominator_positive",),
        unit="美元",
        capability=_MEASURE_CAPABILITIES,
    ),
    "avg_costs": MeasureSpec(
        id="avg_costs",
        display_name="平均成本",
        aggregation_method="ratio",
        numerator="costs_sum",
        denominator="costs_valid_count",
        validity_rules=("denominator_positive",),
        unit="美元",
        capability=_MEASURE_CAPABILITIES,
    ),
    "emergency_rate": MeasureSpec(
        id="emergency_rate",
        display_name="急诊率",
        aggregation_method="ratio",
        numerator="emergency_yes_count",
        denominator="emergency_valid_count",
        validity_rules=(
            "denominator_positive",
            "numerator_not_greater_than_denominator",
        ),
        unit="%",
        capability=_MEASURE_CAPABILITIES,
    ),
    "surgical_rate": MeasureSpec(
        id="surgical_rate",
        display_name="手术相关率",
        aggregation_method="ratio",
        numerator="surgical_yes_count",
        denominator="surgical_valid_count",
        validity_rules=(
            "denominator_positive",
            "numerator_not_greater_than_denominator",
        ),
        unit="%",
        capability=_MEASURE_CAPABILITIES,
    ),
    "severe_rate": MeasureSpec(
        id="severe_rate",
        display_name="重症率",
        aggregation_method="ratio",
        numerator="severe_yes_count",
        denominator="severe_valid_count",
        validity_rules=(
            "denominator_positive",
            "numerator_not_greater_than_denominator",
        ),
        unit="%",
        capability=_MEASURE_CAPABILITIES,
    ),
}


class SemanticRegistry:
    """Resolve canonical semantic IDs without executing any data operation."""

    def __init__(
        self,
        dimensions: Mapping[str, DimensionSpec] | None = None,
        measures: Mapping[str, MeasureSpec] | None = None,
    ) -> None:
        self._dimensions = dict(dimensions or DIMENSION_SPECS)
        self._measures = dict(measures or MEASURE_SPECS)
        self._dimension_aliases: dict[str, str] = {}

        for dimension_id, spec in self._dimensions.items():
            if dimension_id != spec.id:
                raise ValueError("dimension mapping key must match DimensionSpec.id")
            for alias in (spec.id, *spec.aliases):
                normalized = normalize_alias(alias)
                previous = self._dimension_aliases.get(normalized)
                if previous is not None and previous != spec.id:
                    raise ValueError(
                        f"dimension alias is ambiguous: {alias}"
                    )
                self._dimension_aliases[normalized] = spec.id

        self._measure_ids = set(self._measures)
        for measure_id, spec in self._measures.items():
            if measure_id != spec.id:
                raise ValueError("measure mapping key must match MeasureSpec.id")

    @property
    def version(self) -> str:
        return SEMANTIC_REGISTRY_VERSION

    @property
    def dimensions(self) -> dict[str, DimensionSpec]:
        return dict(self._dimensions)

    @property
    def measures(self) -> dict[str, MeasureSpec]:
        return dict(self._measures)

    def normalize_dimension(self, value: str) -> str:
        normalized = normalize_alias(value)
        try:
            return self._dimension_aliases[normalized]
        except KeyError as error:
            raise UnknownDimensionError(f"unknown semantic dimension: {value}") from error

    def get_dimension(self, value: str) -> DimensionSpec:
        return self._dimensions[self.normalize_dimension(value)]

    def validate_measure(self, value: str) -> MeasureSpec:
        if not isinstance(value, str) or not value.strip():
            raise UnknownMeasureError(f"unknown semantic measure: {value}")
        measure_id = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if measure_id not in self._measure_ids:
            raise UnknownMeasureError(f"unknown semantic measure: {value}")
        return self._measures[measure_id]

    def to_document(self) -> dict[str, object]:
        return {
            "version": self.version,
            "dimensions": [
                self._dimensions[key].to_document()
                for key in sorted(self._dimensions)
            ],
            "measures": [
                self._measures[key].to_document()
                for key in sorted(self._measures)
            ],
        }


semantic_registry = SemanticRegistry()


def normalize_dimension(value: str) -> str:
    return semantic_registry.normalize_dimension(value)


def get_dimension(value: str) -> DimensionSpec:
    return semantic_registry.get_dimension(value)


def validate_measure(value: str) -> MeasureSpec:
    return semantic_registry.validate_measure(value)


__all__ = [
    "DIMENSION_SPECS",
    "MEASURE_SPECS",
    "SEMANTIC_REGISTRY_VERSION",
    "SemanticRegistry",
    "get_dimension",
    "normalize_dimension",
    "semantic_registry",
    "validate_measure",
]
