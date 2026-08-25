"""Contracts shared by the Spark aggregate builder and backend repository."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from decimal import Decimal
from numbers import Integral, Real
from typing import Any, Iterable

from .aggregate_registry import (
    DIMENSION_REGISTRY,
    MEASURE_REGISTRY,
    SEMANTIC_REGISTRY_VERSION,
)
from .analytics_snapshot_contract import normalize_utc_timestamp


AGGREGATE_CONTRACT_NAME = "sparcs_aggregate_batch"
AGGREGATE_CONTRACT_VERSION = 1
AGGREGATE_FORMULA_VERSION = "aggregate-additive-v1"
AGGREGATE_SUPPRESSION_POLICY_VERSION = "query-suppression-v1"

AGGREGATE_BATCH_TABLE = "analytics_aggregate_batch"
AGGREGATE_FACT_TABLE = "analytics_aggregate_fact"
AGGREGATE_ACTIVE_BATCH_TABLE = "analytics_aggregate_active_batch"

AGGREGATE_GRAIN = (
    "facility_id",
    "diagnosis_code",
    "age",
    "gender",
    "severity",
    "payment",
    "admission",
)
AGGREGATE_MEASURES = tuple(MEASURE_REGISTRY)
AGGREGATE_BATCH_STATUSES = frozenset(
    {"STAGING", "VALIDATED", "ACTIVE", "RETIRED", "FAILED"}
)
AGGREGATE_STATUS_TRANSITIONS = {
    "STAGING": frozenset({"VALIDATED", "FAILED"}),
    "VALIDATED": frozenset({"ACTIVE", "FAILED"}),
    "ACTIVE": frozenset({"RETIRED"}),
    "RETIRED": frozenset(),
    "FAILED": frozenset(),
}


class AggregateContractError(ValueError):
    """Raised when a candidate batch or fact row violates the contract."""


def validate_status_transition(
    current_status: str,
    target_status: str,
    *,
    rollback: bool = False,
) -> None:
    """Validate one application-owned batch status transition.

    Rollback is deliberately an explicit capability.  It does not make
    ``RETIRED -> ACTIVE`` a normal transition; callers must opt into the
    dedicated rollback path.
    """

    if current_status not in AGGREGATE_BATCH_STATUSES:
        raise AggregateContractError(f"unknown current aggregate status: {current_status}")
    if target_status not in AGGREGATE_BATCH_STATUSES:
        raise AggregateContractError(f"unknown target aggregate status: {target_status}")
    if rollback and (current_status, target_status) == ("RETIRED", "ACTIVE"):
        return
    if target_status not in AGGREGATE_STATUS_TRANSITIONS[current_status]:
        raise AggregateContractError(
            f"illegal aggregate status transition: {current_status} -> {target_status}"
        )


def missing_bucket(field: str) -> str:
    try:
        return DIMENSION_REGISTRY[field]["missing_bucket"]
    except KeyError as error:
        raise AggregateContractError(f"unknown aggregate dimension: {field}") from error


def normalize_dimension_value(field: str, value: Any) -> str:
    """Normalize clean-frame NULL/blank values to a server-owned bucket."""

    if field not in AGGREGATE_GRAIN:
        raise AggregateContractError(f"unknown aggregate dimension: {field}")
    if value is None:
        return missing_bucket(field)
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return missing_bucket(field)
    validate_reserved_token_value(field, value)
    return value


def validate_reserved_token_value(field: str, value: Any) -> None:
    """Reject a real dimension value that would collide with its missing bucket."""

    if field not in AGGREGATE_GRAIN:
        raise AggregateContractError(f"unknown aggregate dimension: {field}")
    if value is None:
        return
    candidate = str(value).strip()
    if candidate and candidate == missing_bucket(field):
        raise AggregateContractError(
            f"reserved missing bucket collision for field '{field}': {candidate}"
        )


def default_suppression_policy(
    minimum_cohort_size: int | None = None,
    *,
    policy_version: str = AGGREGATE_SUPPRESSION_POLICY_VERSION,
) -> dict[str, Any]:
    """Build policy metadata without choosing a final threshold."""

    if minimum_cohort_size is not None:
        if isinstance(minimum_cohort_size, bool) or not isinstance(
            minimum_cohort_size, Integral
        ) or minimum_cohort_size <= 0:
            raise AggregateContractError(
                "minimum_cohort_size must be a positive integer or null"
            )
        minimum_cohort_size = int(minimum_cohort_size)
    return {
        "policy_version": policy_version,
        "mode": "query_time_final_group",
        "minimum_cohort_size": minimum_cohort_size,
        "secondary_suppression": True,
        "same_turn_differencing_protection": True,
        "fact_access": "internal_only",
    }


def _validate_ascii_identifier(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AggregateContractError(f"{field} must be a non-empty trimmed string")
    if len(value) > max_length or not value.isascii() or any(c.isspace() for c in value):
        raise AggregateContractError(f"{field} contains invalid characters")
    return value


def _validate_nonnegative_int(value: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise AggregateContractError(f"{field} must be an integer")
    value = int(value)
    if value < 0 or (positive and value == 0):
        raise AggregateContractError(f"{field} must be non-negative")
    return value


def _validate_nonnegative_number(value: Any, field: str) -> float | int | Decimal:
    if isinstance(value, bool) or not isinstance(value, (Integral, Real, Decimal)):
        raise AggregateContractError(f"{field} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise AggregateContractError(f"{field} cannot be NaN or infinite")
    if value < 0:
        raise AggregateContractError(f"{field} must be non-negative")
    return value


def validate_suppression_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AggregateContractError("suppression_policy must be an object")
    required = {
        "policy_version",
        "mode",
        "minimum_cohort_size",
        "secondary_suppression",
        "same_turn_differencing_protection",
        "fact_access",
    }
    if set(value) != required:
        raise AggregateContractError("suppression_policy has an unfrozen schema")
    policy_version = _validate_ascii_identifier(value["policy_version"], "policy_version", 64)
    if value["mode"] != "query_time_final_group":
        raise AggregateContractError("suppression policy mode is not supported")
    minimum = value["minimum_cohort_size"]
    if minimum is not None:
        _validate_nonnegative_int(minimum, "minimum_cohort_size", positive=True)
    for key in ("secondary_suppression", "same_turn_differencing_protection"):
        if not isinstance(value[key], bool) or not value[key]:
            raise AggregateContractError(f"{key} must be true")
    if value["fact_access"] != "internal_only":
        raise AggregateContractError("aggregate fact access must remain internal_only")
    return {
        **value,
        "policy_version": policy_version,
        "minimum_cohort_size": None if minimum is None else int(minimum),
    }


def validate_source_sha256(expected_sha256: Any, actual_sha256: Any) -> str:
    """Validate that a source digest is a lowercase SHA-256 and matches."""

    for value, label in ((expected_sha256, "expected source_sha256"), (actual_sha256, "actual source_sha256")):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise AggregateContractError(f"{label} must be lowercase SHA-256")
    if expected_sha256 != actual_sha256:
        raise AggregateContractError("source_sha256 does not match the candidate input")
    return expected_sha256


def validate_aggregate_reconciliation(
    *,
    source_scope_row_count: int,
    aggregate_row_count: int,
    fact_row_count: int,
    fact_record_count: int,
) -> dict[str, int]:
    """Require fact cardinality and SUM(record_count) to match the scope."""

    values = {
        "source_scope_row_count": source_scope_row_count,
        "aggregate_row_count": aggregate_row_count,
        "fact_row_count": fact_row_count,
        "fact_record_count": fact_record_count,
    }
    for field, value in values.items():
        _validate_nonnegative_int(value, field)
    if source_scope_row_count <= 0 or aggregate_row_count <= 0:
        raise AggregateContractError("aggregate reconciliation counts must be positive")
    if fact_row_count != aggregate_row_count:
        raise AggregateContractError(
            "aggregate row count does not match the candidate manifest"
        )
    if fact_record_count != source_scope_row_count:
        raise AggregateContractError(
            "SUM(record_count) does not match analysis_scope_row_count"
        )
    return values


def build_batch_id(
    data_version: str,
    formula_version: str,
    registry_version: str,
    suppression_policy_version: str,
) -> str:
    seed = "|".join(
        (data_version, formula_version, registry_version, suppression_policy_version)
    )
    return "agg_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:48]


def build_aggregate_batch_manifest(
    *,
    batch_id: str,
    data_version: str,
    formula_version: str,
    registry_version: str,
    suppression_policy: dict[str, Any],
    input_file_name: str,
    source_sha256: str,
    raw_records: int,
    source_records: int,
    aggregate_rows: int,
    generated_at: str | datetime,
    status: str = "STAGING",
) -> dict[str, Any]:
    return validate_aggregate_batch_manifest(
        {
            "contract": AGGREGATE_CONTRACT_NAME,
            "contract_version": AGGREGATE_CONTRACT_VERSION,
            "batch_id": batch_id,
            "data_version": data_version,
            "formula_version": formula_version,
            "registry_version": registry_version,
            "suppression_policy_version": suppression_policy["policy_version"],
            "suppression_policy": suppression_policy,
            "grain": list(AGGREGATE_GRAIN),
            "measures": list(AGGREGATE_MEASURES),
            "input_file_name": input_file_name,
            "source_sha256": source_sha256,
            "raw_records": raw_records,
            "source_records": source_records,
            "aggregate_rows": aggregate_rows,
            "generated_at": generated_at,
            "status": status,
        }
    )


def validate_aggregate_batch_manifest(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise AggregateContractError("aggregate batch manifest must be an object")
    required = {
        "contract",
        "contract_version",
        "batch_id",
        "data_version",
        "formula_version",
        "registry_version",
        "suppression_policy_version",
        "suppression_policy",
        "grain",
        "measures",
        "input_file_name",
        "source_sha256",
        "raw_records",
        "source_records",
        "aggregate_rows",
        "generated_at",
        "status",
    }
    if set(document) != required:
        raise AggregateContractError("aggregate batch manifest has an unfrozen schema")
    if document["contract"] != AGGREGATE_CONTRACT_NAME:
        raise AggregateContractError("unknown aggregate contract")
    if document["contract_version"] != AGGREGATE_CONTRACT_VERSION:
        raise AggregateContractError("unsupported aggregate contract version")
    batch_id = _validate_ascii_identifier(document["batch_id"], "batch_id", 128)
    data_version = _validate_ascii_identifier(document["data_version"], "data_version", 191)
    formula_version = _validate_ascii_identifier(document["formula_version"], "formula_version", 64)
    registry_version = _validate_ascii_identifier(document["registry_version"], "registry_version", 64)
    suppression_version = _validate_ascii_identifier(
        document["suppression_policy_version"], "suppression_policy_version", 64
    )
    policy = validate_suppression_policy(document["suppression_policy"])
    if policy["policy_version"] != suppression_version:
        raise AggregateContractError("suppression policy version mismatch")
    if formula_version != AGGREGATE_FORMULA_VERSION:
        raise AggregateContractError("unsupported aggregate formula version")
    if registry_version != SEMANTIC_REGISTRY_VERSION:
        raise AggregateContractError("unsupported semantic registry version")
    if document["grain"] != list(AGGREGATE_GRAIN):
        raise AggregateContractError("aggregate grain does not match the frozen contract")
    if document["measures"] != list(AGGREGATE_MEASURES):
        raise AggregateContractError("aggregate measures do not match the frozen contract")
    input_name = document["input_file_name"]
    if (
        not isinstance(input_name, str)
        or not input_name
        or input_name != input_name.strip()
        or "\\" in input_name
        or "/" in input_name
        or len(input_name) > 255
    ):
        raise AggregateContractError("input_file_name must be a basename")
    source_sha256 = document["source_sha256"]
    if (
        not isinstance(source_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
    ):
        raise AggregateContractError("source_sha256 must be lowercase SHA-256")
    raw_records = _validate_nonnegative_int(document["raw_records"], "raw_records")
    source_records = _validate_nonnegative_int(document["source_records"], "source_records", positive=True)
    aggregate_rows = _validate_nonnegative_int(document["aggregate_rows"], "aggregate_rows", positive=True)
    if raw_records < source_records:
        raise AggregateContractError("raw_records cannot be less than source_records")
    timestamp = normalize_utc_timestamp(document["generated_at"])
    status = document["status"]
    if status not in AGGREGATE_BATCH_STATUSES:
        raise AggregateContractError("unknown aggregate batch status")
    return {
        **document,
        "batch_id": batch_id,
        "data_version": data_version,
        "formula_version": formula_version,
        "registry_version": registry_version,
        "suppression_policy_version": suppression_version,
        "suppression_policy": policy,
        "raw_records": raw_records,
        "source_records": source_records,
        "aggregate_rows": aggregate_rows,
        "generated_at": timestamp,
    }


def validate_aggregate_fact_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise AggregateContractError("aggregate fact row must be an object")
    expected = set(AGGREGATE_GRAIN) | set(AGGREGATE_MEASURES)
    if set(row) != expected:
        raise AggregateContractError("aggregate fact row has an unfrozen schema")
    result = dict(row)
    for field in AGGREGATE_GRAIN:
        value = result[field]
        if not isinstance(value, str) or not value or value.strip() != value:
            raise AggregateContractError(f"{field} must be a non-empty normalized string")
        if value == "" or value is None:
            raise AggregateContractError(f"{field} cannot be blank")
    for field in AGGREGATE_MEASURES:
        if field.endswith("_count") or field in {"record_count", "los_sum"}:
            result[field] = _validate_nonnegative_int(result[field], field)
        else:
            result[field] = _validate_nonnegative_number(result[field], field)
    if result["record_count"] == 0:
        raise AggregateContractError("record_count must be positive")
    for field in ("los_valid_count", "charges_valid_count", "costs_valid_count"):
        if result[field] > result["record_count"]:
            raise AggregateContractError(f"{field} cannot exceed record_count")
    if result["emergency_yes_count"] > result["emergency_valid_count"]:
        raise AggregateContractError("emergency_yes_count exceeds emergency_valid_count")
    if result["surgical_yes_count"] > result["surgical_valid_count"]:
        raise AggregateContractError("surgical_yes_count exceeds surgical_valid_count")
    if result["severe_yes_count"] > result["severe_valid_count"]:
        raise AggregateContractError("severe_yes_count exceeds severe_valid_count")
    return result


def validate_fact_rows(rows: Iterable[Any], expected_count: int) -> tuple[int, int]:
    """Validate a stream and return (row_count, source_record_count)."""

    row_count = 0
    source_records = 0
    for row in rows:
        validated = validate_aggregate_fact_row(row)
        row_count += 1
        source_records += validated["record_count"]
    if row_count != expected_count:
        raise AggregateContractError(
            f"fact row count {row_count} does not match manifest {expected_count}"
        )
    return row_count, source_records


def json_safe(value: Any) -> Any:
    """Validate that metadata is JSON-safe before it reaches MySQL JSON."""

    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise AggregateContractError("aggregate metadata is not valid JSON") from error
    return value
