"""Load and validate versioned analytics snapshot acceptance metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_METADATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "acceptance"
    / "snapshot_baselines.json"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STATUSES = frozenset({"current", "historical"})


class SnapshotAcceptanceError(ValueError):
    """Raised when snapshot acceptance metadata is invalid or ambiguous."""


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotAcceptanceError(f"{field} must be a non-empty string")
    return value


def _validate_baseline(baseline_id: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotAcceptanceError(
            f"baselines.{baseline_id} must be an object"
        )

    status = _require_text(value.get("status"), f"baselines.{baseline_id}.status")
    if status not in _STATUSES:
        raise SnapshotAcceptanceError(
            f"baselines.{baseline_id}.status must be current or historical"
        )

    data_version = _require_text(
        value.get("data_version"), f"baselines.{baseline_id}.data_version"
    )
    source_sha256 = _require_text(
        value.get("source_sha256"), f"baselines.{baseline_id}.source_sha256"
    ).lower()
    if _SHA256_PATTERN.fullmatch(source_sha256) is None:
        raise SnapshotAcceptanceError(
            f"baselines.{baseline_id}.source_sha256 must be a lowercase SHA-256"
        )

    analytics_rules_version = _require_text(
        value.get("analytics_rules_version"),
        f"baselines.{baseline_id}.analytics_rules_version",
    )
    snapshot_rows = value.get("snapshot_rows")
    if isinstance(snapshot_rows, bool) or not isinstance(snapshot_rows, int):
        raise SnapshotAcceptanceError(
            f"baselines.{baseline_id}.snapshot_rows must be an integer"
        )
    if snapshot_rows < 0:
        raise SnapshotAcceptanceError(
            f"baselines.{baseline_id}.snapshot_rows must not be negative"
        )

    reason = _require_text(value.get("reason"), f"baselines.{baseline_id}.reason")
    return {
        "status": status,
        "data_version": data_version,
        "source_sha256": source_sha256,
        "analytics_rules_version": analytics_rules_version,
        "snapshot_rows": snapshot_rows,
        "reason": reason,
    }


def load_snapshot_acceptance_metadata(
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Read one metadata document and require exactly one active baseline."""

    metadata_path = Path(path) if path is not None else DEFAULT_METADATA_PATH
    try:
        document = json.loads(metadata_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SnapshotAcceptanceError(
            f"cannot read snapshot acceptance metadata: {metadata_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise SnapshotAcceptanceError(
            f"snapshot acceptance metadata is not valid JSON: {metadata_path}"
        ) from error

    if not isinstance(document, dict):
        raise SnapshotAcceptanceError("snapshot acceptance metadata must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotAcceptanceError(
            f"unsupported snapshot acceptance schema_version: "
            f"{document.get('schema_version')!r}"
        )
    if document.get("table") != "analysis_snapshot_result":
        raise SnapshotAcceptanceError(
            "snapshot acceptance metadata must target analysis_snapshot_result"
        )
    if document.get("metric") != "snapshot_rows":
        raise SnapshotAcceptanceError(
            "snapshot acceptance metadata metric must be snapshot_rows"
        )

    active_baseline_id = _require_text(
        document.get("active_baseline_id"), "active_baseline_id"
    )
    raw_baselines = document.get("baselines")
    if not isinstance(raw_baselines, dict) or not raw_baselines:
        raise SnapshotAcceptanceError("baselines must be a non-empty object")

    baselines: dict[str, dict[str, Any]] = {}
    current_ids: list[str] = []
    for baseline_id, raw_baseline in raw_baselines.items():
        if not isinstance(baseline_id, str) or not baseline_id.strip():
            raise SnapshotAcceptanceError("baseline IDs must be non-empty strings")
        baseline = _validate_baseline(baseline_id, raw_baseline)
        baselines[baseline_id] = baseline
        if baseline["status"] == "current":
            current_ids.append(baseline_id)

    if active_baseline_id not in baselines:
        raise SnapshotAcceptanceError(
            f"active_baseline_id does not exist: {active_baseline_id}"
        )
    if current_ids != [active_baseline_id]:
        raise SnapshotAcceptanceError(
            "metadata must contain exactly one current baseline selected by "
            "active_baseline_id"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "table": document["table"],
        "metric": document["metric"],
        "active_baseline_id": active_baseline_id,
        "baselines": baselines,
    }


def active_snapshot_baseline(
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Return the metadata selected for the current acceptance run."""

    metadata = load_snapshot_acceptance_metadata(path)
    baseline_id = metadata["active_baseline_id"]
    baseline = dict(metadata["baselines"][baseline_id])
    baseline["baseline_id"] = baseline_id
    return baseline
