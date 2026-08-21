"""Leakage-safe inference from an exported PySpark logistic model."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..errors import InvalidRequestError, ResultNotReadyError, ServerMisconfiguredError


FEATURES = (
    "age_group", "gender", "race", "ethnicity", "hospital_service_area",
    "facility_id", "admission_type", "emergency_indicator",
)
LEAKAGE_FIELDS = {
    "total_charges", "total_costs", "length_of_stay", "discharge_disposition",
    "operating_room_procedure", "apr_drg_code", "result", "label", "target",
    "prediction", "surgery", "surgical_procedure", "procedure", "procedures",
    "post_discharge_fields",
}

_REQUIRED_ARTIFACT_FIELDS = frozenset(
    {"intercept", "feature_weights", "model_version", "data_version"}
)


def _request_field_name(value: object) -> str | None:
    """Return the comparison form used for leakage-field detection."""

    if not isinstance(value, str):
        return None
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a numeric value")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("expected a finite numeric value")
    return number


def _sigmoid(score: float) -> float:
    """Calculate sigmoid without overflowing for a malformed/extreme score."""

    if score >= 0:
        exponential = math.exp(-score)
        return 1.0 / (1.0 + exponential)
    exponential = math.exp(score)
    return exponential / (1.0 + exponential)


class HighCostModelService:
    def __init__(self, artifact_path: Path | None) -> None:
        if isinstance(artifact_path, str) and not artifact_path.strip():
            artifact_path = None
        self.artifact_path = Path(artifact_path) if artifact_path else None
        self._artifact: dict | None = None

    def _load(self) -> dict:
        if self._artifact is not None:
            return self._artifact
        if not self.artifact_path:
            raise ResultNotReadyError("high-cost model")
        if not self.artifact_path.exists():
            raise ResultNotReadyError("high-cost model")
        if not self.artifact_path.is_file():
            raise ServerMisconfiguredError()
        try:
            artifact = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ServerMisconfiguredError() from error

        try:
            self._validate_artifact(artifact)
        except (TypeError, ValueError, KeyError) as error:
            raise ServerMisconfiguredError() from error

        self._artifact = artifact
        return artifact

    @staticmethod
    def _validate_artifact(artifact: object) -> None:
        if not isinstance(artifact, dict):
            raise ValueError("the model artifact must be a JSON object")
        if not _REQUIRED_ARTIFACT_FIELDS.issubset(artifact):
            raise ServerMisconfiguredError()

        model_version = artifact["model_version"]
        data_version = artifact["data_version"]
        if (
            not isinstance(model_version, str)
            or not model_version.strip()
            or not isinstance(data_version, str)
            or not data_version.strip()
        ):
            raise ValueError("model and data versions must be non-empty strings")

        _finite_number(artifact["intercept"])
        if "classification_threshold" in artifact:
            threshold = _finite_number(artifact["classification_threshold"])
            if not 0.0 <= threshold <= 1.0:
                raise ValueError("classification threshold must be between 0 and 1")
        if "threshold_amount" in artifact:
            threshold_amount = artifact["threshold_amount"]
            if threshold_amount is None:
                raise ValueError("threshold amount must be numeric")
            if _finite_number(threshold_amount) < 0:
                raise ValueError("threshold amount must be non-negative")

        feature_weights = artifact["feature_weights"]
        if not isinstance(feature_weights, dict) or set(feature_weights) != set(FEATURES):
            raise ValueError("feature weights must cover exactly the public features")
        for feature in FEATURES:
            weights = feature_weights[feature]
            if not isinstance(weights, dict) or not weights:
                raise ValueError(f"weights for {feature} are missing")
            for weight in weights.values():
                _finite_number(weight)

        artifact_type = artifact.get("artifact_type")
        if artifact_type is not None and not isinstance(artifact_type, str):
            raise ValueError("artifact type must be a string")

    def predict(self, document: object) -> dict:
        if not isinstance(document, dict):
            raise InvalidRequestError("INVALID_REQUEST_FORMAT", "A JSON object is required.")

        unknown = [name for name in document if name not in FEATURES]
        leakage = [
            name
            for name in unknown
            if _request_field_name(name) in LEAKAGE_FIELDS
        ]
        if leakage:
            raise InvalidRequestError(
                "LEAKAGE_FIELD_FORBIDDEN",
                "Post-admission or target fields are forbidden.",
                {"fields": sorted(leakage, key=str)},
            )
        if unknown:
            raise InvalidRequestError(
                "INVALID_REQUEST_FIELD",
                "One or more fields are not supported.",
                {"fields": sorted(unknown, key=str)},
            )
        missing = [
            name
            for name in FEATURES
            if not isinstance(document.get(name), str) or not document[name].strip()
        ]
        if missing:
            raise InvalidRequestError(
                "INVALID_REQUEST_FIELD",
                "All admission-time feature fields are required.",
                {"fields": missing},
            )

        artifact = self._load()
        score = _finite_number(artifact["intercept"])
        normalized = {}
        for name in FEATURES:
            value = document[name].strip()
            weights = artifact["feature_weights"].get(name, {})
            if value not in weights:
                if "OTHER" not in weights:
                    raise InvalidRequestError(
                        "INVALID_REQUEST_FIELD",
                        f"The {name} value is not supported.",
                        {"field": name},
                    )
                value = "OTHER"
            normalized[name] = value
            score += _finite_number(weights[value])
        probability = _sigmoid(score)
        threshold = _finite_number(artifact.get("classification_threshold", 0.5))
        data_version = artifact["data_version"]
        return {
            "prediction": "HIGH_COST" if probability >= threshold else "NOT_HIGH_COST",
            "probability": round(probability, 6),
            "classification_threshold": threshold,
            "threshold_amount": artifact.get("threshold_amount"),
            "features": normalized,
            "model_version": artifact["model_version"],
            "data_version": data_version,
            "fixture_only": artifact.get("artifact_type") == "fixture_only" or data_version.startswith("fixture:"),
            "boundary": "Operational classification only; not a diagnosis or treatment recommendation.",
        }
