from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.snapshot_acceptance import (  # noqa: E402
    SnapshotAcceptanceError,
    active_snapshot_baseline,
    load_snapshot_acceptance_metadata,
)


METADATA_PATH = DATA_ROOT / "acceptance" / "snapshot_baselines.json"


def test_current_baseline_is_selected_and_legacy_baseline_is_historical():
    metadata = load_snapshot_acceptance_metadata(METADATA_PATH)
    current = active_snapshot_baseline(METADATA_PATH)

    assert current["status"] == "current"
    assert current["snapshot_rows"] == 7186
    assert current["reason"] == (
        "LIVEBORN/PNL001 excluded by current analytics rule."
    )
    assert current["analytics_rules_version"] == (
        "disease_rules_liveborn_excluded_v1"
    )

    historical = metadata["baselines"][
        "sparcs_2021_20231012__legacy_including_liveborn_v1"
    ]
    assert historical["status"] == "historical"
    assert historical["snapshot_rows"] == 7198
    assert metadata["active_baseline_id"] != (
        "sparcs_2021_20231012__legacy_including_liveborn_v1"
    )


def test_metadata_rejects_more_than_one_current_baseline(tmp_path):
    document = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    document["baselines"]["legacy-copy"] = copy.deepcopy(
        document["baselines"]["sparcs_2021_20231012__legacy_including_liveborn_v1"]
    )
    document["baselines"]["legacy-copy"]["status"] = "current"
    path = tmp_path / "snapshot-baselines.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SnapshotAcceptanceError, match="exactly one current"):
        load_snapshot_acceptance_metadata(path)
