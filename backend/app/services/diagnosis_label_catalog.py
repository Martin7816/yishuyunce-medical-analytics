"""Versioned diagnosis-code labels for safe aggregate evidence display.

The aggregate fact intentionally stores the semantic diagnosis code rather
than a display name.  This catalog reads the already-published disease index
as display metadata only.  It never changes the aggregate query and refuses
to decorate a result when the catalog version does not match the result
version.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import RLock
from typing import Any, Protocol


# The current aggregate batch contains PNL001, while the matching published
# disease-index options intentionally omit that one code.  Keep this tiny
# compatibility alias version-scoped and only use it to fill a missing label;
# a future data version must publish its own mapping or fall back to code.
_VERSIONED_LABEL_FALLBACKS: dict[str, dict[str, str]] = {
    "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219": {
        "PNL001": "LIVEBORN",
    },
}


class DiagnosisLabelResolver(Protocol):
    """Resolve a diagnosis code only within a matching published version."""

    def resolve(self, code: str, data_version: str) -> str | None:
        ...


def _text(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > maximum:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    return value


def _diagnosis_options(snapshot: Mapping[str, Any]) -> dict[str, str]:
    options = snapshot.get("options")
    if not isinstance(options, Mapping):
        return {}

    raw_options = options.get("diagnoses")
    if not isinstance(raw_options, Sequence) or isinstance(
        raw_options, (str, bytes, bytearray)
    ):
        raw_options = options.get("diagnosis_code")
    if not isinstance(raw_options, Sequence) or isinstance(
        raw_options, (str, bytes, bytearray)
    ):
        return {}

    labels: dict[str, str] = {}
    for raw_item in raw_options:
        if not isinstance(raw_item, Mapping):
            continue
        code = _text(raw_item.get("value"), maximum=64)
        label = _text(raw_item.get("label"), maximum=255)
        if code is None or label is None:
            continue
        previous = labels.get(code)
        if previous is not None and previous != label:
            # An ambiguous catalog must not silently choose one label.
            labels.pop(code, None)
            continue
        labels[code] = label
    return labels


class SnapshotDiagnosisLabelCatalog:
    """Lazy, fail-closed resolver backed by the published disease index.

    A failed snapshot read is deliberately treated as a display fallback,
    not as an analytics-query failure.  The requested result version is part
    of the cache key so a newly activated batch cannot inherit stale labels.
    """

    def __init__(
        self,
        snapshot_service,
        *,
        module_key: str = "diseases",
        entity_key: str = "index",
    ) -> None:
        self.snapshot_service = snapshot_service
        self.module_key = module_key
        self.entity_key = entity_key
        self._lock = RLock()
        self._loaded_for_version: str | None = None
        self._catalog_version: str | None = None
        self._labels: dict[str, str] = {}

    def _refresh(self, requested_version: str) -> None:
        labels: dict[str, str] = {}
        catalog_version: str | None = None
        try:
            snapshot = self.snapshot_service.get(self.module_key, self.entity_key)
            if isinstance(snapshot, Mapping):
                catalog_version = _text(snapshot.get("data_version"), maximum=256)
                labels = _diagnosis_options(snapshot)
                for code, label in _VERSIONED_LABEL_FALLBACKS.get(
                    catalog_version or "", {}
                ).items():
                    labels.setdefault(code, label)
        except Exception:
            # Display metadata is optional.  Never make a safe aggregate
            # result unavailable because the label source is unavailable.
            labels = {}
            catalog_version = None

        self._loaded_for_version = requested_version
        self._catalog_version = catalog_version
        self._labels = labels

    def resolve(self, code: str, data_version: str) -> str | None:
        code = _text(code, maximum=64) or ""
        requested_version = _text(data_version, maximum=256) or ""
        if not code or not requested_version:
            return None

        with self._lock:
            if self._loaded_for_version != requested_version:
                self._refresh(requested_version)
            if self._catalog_version != requested_version:
                return None
            return self._labels.get(code)


__all__ = ["DiagnosisLabelResolver", "SnapshotDiagnosisLabelCatalog"]
