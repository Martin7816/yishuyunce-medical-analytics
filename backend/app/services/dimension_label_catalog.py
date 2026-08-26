"""Version-matched display labels for aggregate dimensions.

Semantic aggregate facts intentionally keep stable codes. This module reads
already-published snapshot options as optional display metadata and refuses to
mix labels from a different data version. A metadata failure never makes the
underlying aggregate query unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import RLock
from typing import Any, Protocol


class DimensionLabelResolver(Protocol):
    """Resolve a dimension code only within a matching published version."""

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


def _option_labels(
    snapshot: Mapping[str, Any],
    option_names: Sequence[str],
) -> dict[str, str]:
    options = snapshot.get("options")
    if not isinstance(options, Mapping):
        return {}

    raw_options: object = None
    for option_name in option_names:
        candidate = options.get(option_name)
        if isinstance(candidate, Sequence) and not isinstance(
            candidate, (str, bytes, bytearray)
        ):
            raw_options = candidate
            break
    if not isinstance(raw_options, Sequence) or isinstance(
        raw_options, (str, bytes, bytearray)
    ):
        return {}

    labels: dict[str, str] = {}
    ambiguous: set[str] = set()
    for raw_item in raw_options:
        if not isinstance(raw_item, Mapping):
            continue
        code = _text(raw_item.get("value"), maximum=64)
        label = _text(raw_item.get("label"), maximum=255)
        if code is None or label is None or code in ambiguous:
            continue
        previous = labels.get(code)
        if previous is not None and previous != label:
            labels.pop(code, None)
            ambiguous.add(code)
            continue
        labels[code] = label
    return labels


class SnapshotOptionLabelCatalog:
    """Lazy, fail-closed resolver backed by one published snapshot index."""

    def __init__(
        self,
        snapshot_service,
        *,
        module_key: str,
        entity_key: str,
        option_names: Sequence[str],
        versioned_fallbacks: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.snapshot_service = snapshot_service
        self.module_key = module_key
        self.entity_key = entity_key
        self.option_names = tuple(option_names)
        self.versioned_fallbacks = versioned_fallbacks or {}
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
                labels = _option_labels(snapshot, self.option_names)
                for code, label in self.versioned_fallbacks.get(
                    catalog_version or "", {}
                ).items():
                    labels.setdefault(code, label)
        except Exception:
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


__all__ = ["DimensionLabelResolver", "SnapshotOptionLabelCatalog"]
