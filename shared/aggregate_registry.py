"""Server-owned semantic registry for the internal aggregate fact.

The registry deliberately describes names and formulas only.  It does not
execute queries and it does not expose the physical fact table to callers.
Keeping this metadata versioned gives a future query planner one stable source
for semantic names without putting planner logic into the Spark job.
"""

from __future__ import annotations

from copy import deepcopy


SEMANTIC_REGISTRY_VERSION = "aggregate-registry-v1"


DIMENSION_REGISTRY = {
    "facility_id": {
        "semantic_name": "hospital",
        "source_field": "facility_id",
        "data_type": "string",
        "missing_bucket": "__MISSING_FACILITY_ID__",
        "filterable": True,
    },
    "diagnosis_code": {
        "semantic_name": "diagnosis",
        "source_field": "diagnosis_code",
        "data_type": "string",
        "missing_bucket": "__MISSING_DIAGNOSIS_CODE__",
        "filterable": True,
    },
    "age": {
        "semantic_name": "age_group",
        "source_field": "age",
        "data_type": "string",
        "missing_bucket": "__MISSING_AGE__",
        "filterable": True,
    },
    "gender": {
        "semantic_name": "gender",
        "source_field": "gender",
        "data_type": "string",
        "missing_bucket": "__MISSING_GENDER__",
        "filterable": True,
    },
    "severity": {
        "semantic_name": "severity",
        "source_field": "severity",
        "data_type": "string",
        "missing_bucket": "__MISSING_SEVERITY__",
        "filterable": True,
    },
    "payment": {
        "semantic_name": "payment",
        "source_field": "payment",
        "data_type": "string",
        "missing_bucket": "__MISSING_PAYMENT__",
        "filterable": True,
    },
    "admission": {
        "semantic_name": "admission",
        "source_field": "admission",
        "data_type": "string",
        "missing_bucket": "__MISSING_ADMISSION__",
        "filterable": True,
    },
}


MEASURE_REGISTRY = {
    "record_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(*)",
    },
    "los_sum": {
        "data_type": "integer",
        "additive": True,
        "formula": "SUM(los)",
    },
    "los_valid_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(los)",
    },
    "charges_sum": {
        "data_type": "decimal",
        "additive": True,
        "formula": "SUM(charges WHERE valid_money)",
    },
    "charges_valid_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(charges WHERE valid_money)",
    },
    "costs_sum": {
        "data_type": "decimal",
        "additive": True,
        "formula": "SUM(costs WHERE valid_money)",
    },
    "costs_valid_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(costs WHERE valid_money)",
    },
    "emergency_yes_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "SUM(emergency = 'Y')",
    },
    "emergency_valid_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(emergency WHERE non-empty)",
    },
    "surgical_yes_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "SUM(medical_surgical CONTAINS 'Surgical')",
    },
    "surgical_valid_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(medical_surgical WHERE non-empty)",
    },
    "severe_yes_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "SUM(severity IN ('Major', 'Extreme'))",
    },
    "severe_valid_count": {
        "data_type": "integer",
        "additive": True,
        "formula": "COUNT(severity IN ('Minor', 'Moderate', 'Major', 'Extreme'))",
    },
}


def registry_document() -> dict:
    """Return a copy suitable for batch metadata or audit output."""

    return {
        "version": SEMANTIC_REGISTRY_VERSION,
        "dimensions": deepcopy(DIMENSION_REGISTRY),
        "measures": deepcopy(MEASURE_REGISTRY),
    }
