from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ROOT / "src"))

from publish_analytics_snapshot_mysql import load_snapshot  # noqa: E402


def test_fixture_is_valid_publishable_snapshot():
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = load_snapshot(path)
    assert document["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert len({(row["module_key"], row["entity_key"]) for row in document["records"]}) == len(document["records"])


def test_duplicate_snapshot_key_is_rejected(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["records"].append(document["records"][0])
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        load_snapshot(invalid)
