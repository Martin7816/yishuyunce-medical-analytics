from __future__ import annotations

import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DATA_ROOT / "src"))

from shared.aggregate_contract import (  # noqa: E402
    AGGREGATE_FORMULA_VERSION,
    AGGREGATE_MEASURES,
    AggregateContractError,
    build_aggregate_batch_manifest,
    build_batch_id,
    default_suppression_policy,
    normalize_dimension_value,
    validate_aggregate_reconciliation,
    validate_aggregate_batch_manifest,
    validate_aggregate_fact_row,
    validate_reserved_token_value,
    validate_source_sha256,
    validate_status_transition,
)
from shared.aggregate_registry import SEMANTIC_REGISTRY_VERSION  # noqa: E402


def _manifest(**overrides):
    policy = default_suppression_policy()
    values = {
        "batch_id": build_batch_id(
            "fixture:test:v1",
            AGGREGATE_FORMULA_VERSION,
            SEMANTIC_REGISTRY_VERSION,
            policy["policy_version"],
        ),
        "data_version": "fixture:test:v1",
        "formula_version": AGGREGATE_FORMULA_VERSION,
        "registry_version": SEMANTIC_REGISTRY_VERSION,
        "suppression_policy": policy,
        "input_file_name": "sample.csv",
        "source_sha256": "a" * 64,
        "raw_records": 3,
        "source_records": 2,
        "aggregate_rows": 2,
        "generated_at": "2026-08-24T00:00:00Z",
    }
    values.update(overrides)
    return build_aggregate_batch_manifest(**values)


def _fact_row(**overrides):
    row = {
        "facility_id": "F001",
        "diagnosis_code": "RSP009",
        "age": "0 to 17",
        "gender": "F",
        "severity": "Major",
        "payment": "Medicare",
        "admission": "Emergency",
        "record_count": 2,
        "los_sum": 5,
        "los_valid_count": 2,
        "charges_sum": 100.5,
        "charges_valid_count": 1,
        "costs_sum": 50.25,
        "costs_valid_count": 1,
        "emergency_yes_count": 1,
        "emergency_valid_count": 2,
        "surgical_yes_count": 0,
        "surgical_valid_count": 2,
        "severe_yes_count": 1,
        "severe_valid_count": 2,
    }
    row.update(overrides)
    return row


def test_dimension_missing_values_use_reserved_server_bucket():
    assert normalize_dimension_value("facility_id", None) == "__MISSING_FACILITY_ID__"
    assert normalize_dimension_value("diagnosis_code", "   ") == "__MISSING_DIAGNOSIS_CODE__"
    assert normalize_dimension_value("gender", " F ") == "F"


def test_reserved_dimension_token_collision_fails_closed():
    with pytest.raises(AggregateContractError, match="facility_id"):
        validate_reserved_token_value("facility_id", " __MISSING_FACILITY_ID__ ")


def test_source_sha_and_reconciliation_are_explicit_contract_checks():
    digest = "a" * 64
    assert validate_source_sha256(digest, digest) == digest
    with pytest.raises(AggregateContractError, match="source_sha256"):
        validate_source_sha256(digest, "b" * 64)
    assert validate_aggregate_reconciliation(
        source_scope_row_count=10,
        aggregate_row_count=4,
        fact_row_count=4,
        fact_record_count=10,
    )["fact_record_count"] == 10
    with pytest.raises(AggregateContractError, match="analysis_scope_row_count"):
        validate_aggregate_reconciliation(
            source_scope_row_count=10,
            aggregate_row_count=4,
            fact_row_count=4,
            fact_record_count=9,
        )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("STAGING", "VALIDATED"),
        ("STAGING", "FAILED"),
        ("VALIDATED", "ACTIVE"),
        ("VALIDATED", "FAILED"),
        ("ACTIVE", "RETIRED"),
    ],
)
def test_legal_status_transitions(current, target):
    validate_status_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("RETIRED", "ACTIVE"),
        ("FAILED", "ACTIVE"),
        ("ACTIVE", "STAGING"),
        ("VALIDATED", "STAGING"),
    ],
)
def test_illegal_status_transitions_fail_closed(current, target):
    with pytest.raises(AggregateContractError, match="transition"):
        validate_status_transition(current, target)


def test_retired_to_active_requires_explicit_rollback_path():
    validate_status_transition("RETIRED", "ACTIVE", rollback=True)


def test_batch_manifest_freezes_versions_grain_measures_and_policy():
    manifest = _manifest()
    assert manifest["status"] == "STAGING"
    assert manifest["registry_version"] == SEMANTIC_REGISTRY_VERSION
    assert manifest["suppression_policy"]["minimum_cohort_size"] is None
    assert manifest["measures"] == list(AGGREGATE_MEASURES)
    assert validate_aggregate_batch_manifest(manifest) == manifest


def test_batch_manifest_rejects_policy_version_mismatch():
    manifest = _manifest()
    manifest["suppression_policy_version"] = "query-suppression-other-v1"
    with pytest.raises(AggregateContractError, match="version mismatch"):
        validate_aggregate_batch_manifest(manifest)


def test_fact_row_requires_normalized_dimensions_and_additive_counts():
    assert validate_aggregate_fact_row(_fact_row())["record_count"] == 2
    with pytest.raises(AggregateContractError, match="non-empty normalized"):
        validate_aggregate_fact_row(_fact_row(gender=""))
    with pytest.raises(AggregateContractError, match="cannot exceed"):
        validate_aggregate_fact_row(_fact_row(charges_valid_count=3))


def test_fact_row_rejects_negative_measure():
    with pytest.raises(AggregateContractError, match="non-negative"):
        validate_aggregate_fact_row(_fact_row(charges_sum=-1))
