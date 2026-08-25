from __future__ import annotations

import pytest

from app.services.semantic_registry import (
    DIMENSION_SPECS,
    MEASURE_SPECS,
    get_dimension,
    normalize_dimension,
    validate_measure,
)
from shared.query_semantic_contract import (
    UnknownDimensionError,
    UnknownMeasureError,
)


@pytest.mark.parametrize(
    ("dimension_id", "physical_field"),
    [(dimension_id, spec.physical_field) for dimension_id, spec in DIMENSION_SPECS.items()],
)
def test_known_dimension_is_accepted_and_maps_to_physical_field(
    dimension_id: str, physical_field: str
):
    dimension = get_dimension(dimension_id)

    assert dimension.id == dimension_id
    assert dimension.physical_field == physical_field
    assert dimension.type == "enum"
    assert "eq" in dimension.allowed_operators
    assert dimension.capability


def test_unknown_dimension_is_rejected():
    with pytest.raises(UnknownDimensionError, match="unknown semantic dimension"):
        get_dimension("patient")


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("医院", "hospital"),
        ("Facility", "hospital"),
        ("诊断", "diagnosis"),
        ("age-group", "age_group"),
        ("支付方式", "payment"),
        ("Admission Type", "admission_type"),
    ],
)
def test_alias_normalization(alias: str, expected: str):
    assert normalize_dimension(alias) == expected


@pytest.mark.parametrize("measure_id", sorted(MEASURE_SPECS))
def test_measure_validation_accepts_supported_measure(measure_id: str):
    measure = validate_measure(measure_id)

    assert measure.id == measure_id
    assert measure.aggregation_method in {"sum", "ratio"}
    assert measure.numerator
    assert measure.validity_rules


def test_unknown_measure_is_rejected():
    with pytest.raises(UnknownMeasureError, match="unknown semantic measure"):
        validate_measure("average_patient_risk")
