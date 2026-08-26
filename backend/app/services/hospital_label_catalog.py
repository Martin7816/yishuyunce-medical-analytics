"""Versioned hospital-code labels for safe aggregate evidence display."""

from __future__ import annotations

from typing import Protocol

from .dimension_label_catalog import (
    DimensionLabelResolver,
    SnapshotOptionLabelCatalog,
)


class HospitalLabelResolver(DimensionLabelResolver, Protocol):
    """Resolve a hospital code only within a matching published version."""


class SnapshotHospitalLabelCatalog(SnapshotOptionLabelCatalog):
    """Resolve hospital codes from the matching published hospital index."""

    def __init__(self, snapshot_service) -> None:
        super().__init__(
            snapshot_service,
            module_key="hospitals",
            entity_key="index",
            option_names=("facilities",),
        )


__all__ = ["HospitalLabelResolver", "SnapshotHospitalLabelCatalog"]
