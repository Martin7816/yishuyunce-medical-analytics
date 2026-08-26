"""Versioned diagnosis-code labels for safe aggregate evidence display."""

from __future__ import annotations

from typing import Protocol

from .dimension_label_catalog import (
    DimensionLabelResolver,
    SnapshotOptionLabelCatalog,
)


_VERSIONED_LABEL_FALLBACKS: dict[str, dict[str, str]] = {
    "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219": {
        "PNL001": "LIVEBORN",
    },
}


class DiagnosisLabelResolver(DimensionLabelResolver, Protocol):
    """Resolve a diagnosis code only within a matching published version."""


class SnapshotDiagnosisLabelCatalog(SnapshotOptionLabelCatalog):
    """Resolve diagnosis codes from the matching published disease index."""

    def __init__(self, snapshot_service) -> None:
        super().__init__(
            snapshot_service,
            module_key="diseases",
            entity_key="index",
            option_names=("diagnoses", "diagnosis_code"),
            versioned_fallbacks=_VERSIONED_LABEL_FALLBACKS,
        )


__all__ = ["DiagnosisLabelResolver", "SnapshotDiagnosisLabelCatalog"]
