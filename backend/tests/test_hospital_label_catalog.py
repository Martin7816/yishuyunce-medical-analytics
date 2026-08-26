from __future__ import annotations

from app.services.hospital_label_catalog import SnapshotHospitalLabelCatalog


DATA_VERSION = "aggregate:v1"


class FakeSnapshotService:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error
        self.calls = []

    def get(self, module_key, entity_key):
        self.calls.append((module_key, entity_key))
        if self.error is not None:
            raise self.error
        return self.snapshot


def test_matching_snapshot_version_resolves_hospital_label():
    service = FakeSnapshotService(
        {
            "data_version": DATA_VERSION,
            "options": {
                "facilities": [
                    {
                        "value": "000541",
                        "label": "North Shore University Hospital",
                    },
                ]
            },
        }
    )
    catalog = SnapshotHospitalLabelCatalog(service)

    assert (
        catalog.resolve("000541", DATA_VERSION)
        == "North Shore University Hospital"
    )
    assert catalog.resolve("000541", DATA_VERSION) == "North Shore University Hospital"
    assert service.calls == [("hospitals", "index")]


def test_hospital_catalog_version_mismatch_fails_closed():
    service = FakeSnapshotService(
        {
            "data_version": "aggregate:old",
            "options": {
                "facilities": [
                    {
                        "value": "000541",
                        "label": "North Shore University Hospital",
                    },
                ]
            },
        }
    )

    assert SnapshotHospitalLabelCatalog(service).resolve("000541", DATA_VERSION) is None


def test_hospital_catalog_unavailable_falls_back_without_raising():
    catalog = SnapshotHospitalLabelCatalog(
        FakeSnapshotService(error=RuntimeError("snapshot unavailable"))
    )

    assert catalog.resolve("000541", DATA_VERSION) is None
