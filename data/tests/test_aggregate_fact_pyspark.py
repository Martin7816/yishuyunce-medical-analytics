from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(DATA_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from aggregate_fact_pyspark import _write_candidate  # noqa: E402
from shared.aggregate_contract import (  # noqa: E402
    AGGREGATE_GRAIN,
    AGGREGATE_MEASURES,
)


class _FakeFact:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def toPandas(self) -> pd.DataFrame:
        return self._frame

    @property
    def write(self):
        raise AssertionError("candidate writer must not use Spark Hadoop output")


def test_write_candidate_uses_local_pandas_json_lines(tmp_path):
    row = {field: f"{field}-value" for field in AGGREGATE_GRAIN}
    row.update(
        {
            "record_count": 2,
            "los_sum": 5,
            "los_valid_count": 2,
            "charges_sum": 10.25,
            "charges_valid_count": 2,
            "costs_sum": 8.5,
            "costs_valid_count": 2,
            "emergency_yes_count": 1,
            "emergency_valid_count": 2,
            "surgical_yes_count": 0,
            "surgical_valid_count": 1,
            "severe_yes_count": 1,
            "severe_valid_count": 2,
        }
    )
    assert set(row) == set(AGGREGATE_GRAIN) | set(AGGREGATE_MEASURES)
    manifest = {
        "batch_id": "test-batch",
        "status": "STAGING",
        "aggregate_rows": 1,
        "source_records": 2,
    }
    output_dir = tmp_path / "candidate"

    _write_candidate(output_dir, _FakeFact(pd.DataFrame([row])), manifest)

    assert json.loads((output_dir / "manifest.json").read_text()) == manifest
    facts = [
        json.loads(line)
        for line in (output_dir / "facts.json").read_text().splitlines()
        if line.strip()
    ]
    assert facts == [row]
