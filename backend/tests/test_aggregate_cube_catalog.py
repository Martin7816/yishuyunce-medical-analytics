from __future__ import annotations

from app.services.aggregate_cube_catalog import (
    aggregate_cube_shapes,
    resolve_aggregate_cube_shape,
    supports_aggregate_cube_shape,
)


def test_cube_catalog_exposes_reviewed_cross_dimension_rollups() -> None:
    age_gender_disease = resolve_aggregate_cube_shape(
        ("age_group", "gender", "diagnosis")
    )
    hospital_age_disease = resolve_aggregate_cube_shape(
        ("hospital", "age_group", "diagnosis")
    )

    assert age_gender_disease is not None
    assert (
        age_gender_disease.source_capability
        == "aggregate_age_group_gender_diagnosis"
    )
    assert hospital_age_disease is not None
    assert (
        hospital_age_disease.source_capability
        == "aggregate_hospital_age_group_diagnosis"
    )


def test_cube_catalog_requires_exact_reviewed_shape() -> None:
    assert supports_aggregate_cube_shape(("diagnosis", "gender", "age_group"))
    assert not supports_aggregate_cube_shape(("hospital", "payment", "diagnosis"))
    assert resolve_aggregate_cube_shape(("raw_patient_id",)) is None


def test_cube_catalog_has_unique_capability_names_and_dimension_sets() -> None:
    shapes = aggregate_cube_shapes()

    assert len({shape.source_capability for shape in shapes}) == len(shapes)
    assert len({shape.dimensions for shape in shapes}) == len(shapes)
