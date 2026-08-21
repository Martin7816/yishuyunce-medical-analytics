from __future__ import annotations

import math
import sys
from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ROOT / "src"))

from train_high_cost_model_pyspark import (  # noqa: E402
    EXCLUDED_INPUT_COLUMNS,
    FEATURES,
    PUBLIC_NAMES,
    PUBLIC_LEAKAGE_FIELDS,
    _classification_metrics,
    _snapshot_payload,
    compare_repetitions,
)
from run_full_analytics_pyspark import FIELD_ALIASES, FIELDS  # noqa: E402


def _result(f1: float = 0.5) -> dict:
    feature_names = list(PUBLIC_NAMES.values())
    feature_weights = {name: {"OTHER": 0.0} for name in feature_names}
    feature_metadata = {
        name: {
            "input_column": source,
            "categories": [],
            "learned_category_size": 0,
            "encoder_category_size": 1,
            "encoded_width": 2,
            "unknown_bucket": "OTHER",
            "unknown_index": 0,
            "encoder_invalid_index": 1,
            "encoder_invalid_weight": 0.0,
            "weights": {"OTHER": 0.0},
        }
        for source, name in PUBLIC_NAMES.items()
    }
    metrics = {
        "model_version": "model:v1",
        "data_version": "data:v1",
        "threshold_amount": 10.0,
        "train_rows": 8,
        "test_rows": 2,
        "accuracy": 0.5,
        "precision": 0.5,
        "recall": 0.5,
        "f1": f1,
        "auc": 0.5,
        "confusion_matrix": {"tn": 1, "fp": 0, "fn": 1, "tp": 0},
    }
    artifact = {
        "feature_names": feature_names,
        "feature_weights": feature_weights,
        "feature_metadata": feature_metadata,
        "coefficient_count": 16,
    }
    return {"artifact": artifact, "metrics": metrics}


def test_model_feature_allowlist_is_exactly_eight_and_excludes_target_inputs():
    assert len(FEATURES) == 8
    assert list(PUBLIC_NAMES.values()) == [
        "age_group",
        "gender",
        "race",
        "ethnicity",
        "hospital_service_area",
        "facility_id",
        "admission_type",
        "emergency_indicator",
    ]
    assert not set(FEATURES) & set(EXCLUDED_INPUT_COLUMNS)
    assert {"charges", "costs", "los", "disposition"} <= set(EXCLUDED_INPUT_COLUMNS)
    assert "total_charges" in PUBLIC_LEAKAGE_FIELDS


def test_real_sparcs_service_area_column_is_mapped_with_legacy_fallback():
    assert FIELDS["area"] == "Hospital Service Area"
    assert FIELD_ALIASES["area"] == ("Hospital Service Area", "Health Service Area")


def test_zero_denominators_return_stable_zero_metrics():
    metrics = _classification_metrics(
        {"n": 2, "tp": 0, "fp": 0, "fn": 0, "tn": 2},
        math.nan,
    )

    assert metrics["accuracy"] == 1.0
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0
    assert metrics["auc"] == 0.0


def test_repeated_results_compare_all_published_metrics_and_coefficients():
    first = _result()
    second = _result()
    comparison = compare_repetitions([first, second])

    assert comparison["status"] == "PASS"
    assert all(comparison["checks"].values())
    assert comparison["coefficient_max_abs_delta"] == 0.0

    second["metrics"]["f1"] = 0.6
    failed = compare_repetitions([first, second])
    assert failed["status"] == "FAIL"
    assert failed["checks"]["f1"] is False


def test_snapshot_payload_keeps_model_metadata_under_options():
    result = _result()
    result["artifact"].update(
        {
            "model_version": "model:v1",
            "data_version": "data:v1",
            "threshold_amount": 10.0,
            "classification_threshold": 0.5,
            "artifact_type": "pyspark_logistic_regression",
        }
    )
    payload = _snapshot_payload(result["metrics"], result["artifact"])

    assert payload["options"]["model_version"] == "model:v1"
    assert payload["options"]["data_version"] == "data:v1"
    assert [metric["key"] for metric in payload["metrics"]] == [
        "train_rows",
        "test_rows",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "auc",
    ]
    assert payload["sections"][0]["key"] == "confusion"
