"""Leakage-safe inference from an exported PySpark logistic model."""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..errors import InvalidRequestError, ResultNotReadyError, ServerMisconfiguredError


FEATURES = (
    "age_group", "gender", "race", "ethnicity", "hospital_service_area",
    "facility_id", "admission_type", "emergency_indicator",
)
LEAKAGE_FIELDS = {
    "total_charges", "total_costs", "length_of_stay", "discharge_disposition",
    "operating_room_procedure", "apr_drg_code", "result",
}


class HighCostModelService:
    def __init__(self, artifact_path: Path | None) -> None:
        self.artifact_path = Path(artifact_path) if artifact_path else None
        self._artifact: dict | None = None

    def _load(self) -> dict:
        if self._artifact is not None:
            return self._artifact
        if not self.artifact_path or not self.artifact_path.exists():
            raise ResultNotReadyError("high-cost model")
        try:
            artifact = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ServerMisconfiguredError() from error
        if not all(key in artifact for key in ("intercept", "feature_weights", "model_version", "data_version")):
            raise ServerMisconfiguredError()
        self._artifact = artifact
        return artifact

    def predict(self, document: object) -> dict:
        if not isinstance(document, dict):
            raise InvalidRequestError("INVALID_REQUEST_FORMAT", "A JSON object is required.")
        unknown = sorted(set(document) - set(FEATURES))
        if set(unknown) & LEAKAGE_FIELDS:
            raise InvalidRequestError("LEAKAGE_FIELD_FORBIDDEN", "Post-admission or target fields are forbidden.", {"fields": unknown})
        if unknown:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "One or more fields are not supported.", {"fields": unknown})
        missing = [name for name in FEATURES if not isinstance(document.get(name), str) or not document[name].strip()]
        if missing:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "All admission-time feature fields are required.", {"fields": missing})

        artifact = self._load()
        score = float(artifact["intercept"])
        normalized = {}
        for name in FEATURES:
            value = document[name].strip()
            weights = artifact["feature_weights"].get(name, {})
            if value not in weights:
                if "OTHER" not in weights:
                    raise InvalidRequestError("INVALID_FEATURE_VALUE", f"The {name} value is not supported.", {"field": name})
                value = "OTHER"
            normalized[name] = value
            score += float(weights[value])
        probability = 1.0 / (1.0 + math.exp(-score))
        threshold = float(artifact.get("classification_threshold", 0.5))
        return {
            "prediction": "HIGH_COST" if probability >= threshold else "NOT_HIGH_COST",
            "probability": round(probability, 6),
            "classification_threshold": threshold,
            "threshold_amount": artifact.get("threshold_amount"),
            "features": normalized,
            "model_version": artifact["model_version"],
            "data_version": artifact["data_version"],
            "fixture_only": artifact.get("artifact_type") == "fixture_only",
            "boundary": "Operational classification only; not a diagnosis or treatment recommendation.",
        }
