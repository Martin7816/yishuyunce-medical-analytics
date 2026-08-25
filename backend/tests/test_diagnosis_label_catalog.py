from __future__ import annotations

from app.services.diagnosis_label_catalog import SnapshotDiagnosisLabelCatalog


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


def test_matching_snapshot_version_resolves_diagnosis_label():
    service = FakeSnapshotService(
        {
            "data_version": DATA_VERSION,
            "options": {
                "diagnoses": [
                    {"value": "CIR019", "label": "HEART FAILURE"},
                ]
            },
        }
    )
    catalog = SnapshotDiagnosisLabelCatalog(service)

    assert catalog.resolve("CIR019", DATA_VERSION) == "HEART FAILURE"
    assert catalog.resolve("CIR019", DATA_VERSION) == "HEART FAILURE"
    assert service.calls == [("diseases", "index")]


def test_version_mismatch_fails_closed_without_label():
    service = FakeSnapshotService(
        {
            "data_version": "aggregate:old",
            "options": {
                "diagnoses": [
                    {"value": "CIR019", "label": "HEART FAILURE"},
                ]
            },
        }
    )
    catalog = SnapshotDiagnosisLabelCatalog(service)

    assert catalog.resolve("CIR019", DATA_VERSION) is None


def test_unavailable_snapshot_falls_back_without_raising():
    catalog = SnapshotDiagnosisLabelCatalog(
        FakeSnapshotService(error=RuntimeError("snapshot unavailable"))
    )

    assert catalog.resolve("CIR019", DATA_VERSION) is None


def test_current_published_compatibility_label_is_version_scoped():
    current_version = (
        "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219"
    )
    service = FakeSnapshotService(
        {
            "data_version": current_version,
            "options": {"diagnoses": []},
        }
    )
    catalog = SnapshotDiagnosisLabelCatalog(service)

    assert catalog.resolve("PNL001", current_version) == "LIVEBORN"
    assert catalog.resolve("PNL001", DATA_VERSION) is None
