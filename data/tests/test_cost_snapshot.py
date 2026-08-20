from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(DATA_ROOT / "src"))

from verify_cost_snapshot import (  # noqa: E402
    WILDCARD,
    expected_metric_values,
    summarize_stream,
)


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_cost_independent_formula_and_legal_key_matrix():
    with EDGE_SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))

    assert raw_rows == 4
    assert scoped_rows == 3
    assert expected["diagnosis_values"] == ["END003", "RSP009"]
    assert expected["facility_values"] == ["F001", "F002"]
    assert expected["severity_values"] == ["Extreme", "Major"]
    assert len(expected["expected_keys"]) == 15

    wildcard = expected["aggregates"][WILDCARD]
    assert expected_metric_values(wildcard, include_quantiles=True) == {
        "record_count": 2,
        "avg_charges": 150.0,
        "median_charges": 100.0,
        "p25_charges": 100.0,
        "p75_charges": 200.0,
        "p90_charges": 200.0,
        "avg_costs": 60.0,
        "median_costs": 20.0,
        "p25_costs": 20.0,
        "p75_costs": 100.0,
        "p90_costs": 100.0,
        "charge_cost_gap": 90.0,
        "daily_charges": 50.0,
        "daily_costs": 17.5,
    }


def test_pyspark_cost_snapshot_matches_independent_verifier(tmp_path):
    pytest.importorskip("pyspark")
    snapshot_path = tmp_path / "cost-snapshot.json"
    environment = os.environ.copy()
    environment["PYSPARK_PYTHON"] = sys.executable
    environment["PYSPARK_DRIVER_PYTHON"] = sys.executable
    environment["SPARK_LOCAL_IP"] = "127.0.0.1"

    generated = subprocess.run(
        [
            sys.executable,
            str(DATA_ROOT / "src" / "run_full_analytics_pyspark.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--output",
            str(snapshot_path),
            "--generated-at",
            "2026-08-19T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert generated.returncode == 0, generated.stderr + generated.stdout

    verified = subprocess.run(
        [
            sys.executable,
            str(DATA_ROOT / "src" / "verify_cost_snapshot.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--snapshot",
            str(snapshot_path),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert verified.returncode == 0, verified.stderr + verified.stdout
    result = json.loads(verified.stdout)
    assert result["status"] == "PASS"
    assert result["cost_key_count"] == 15
    assert result["nonempty_combination_count"] == 6
    assert result["empty_combination_count"] == 9

    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    costs = [record for record in document["records"] if record["module_key"] == "costs"]
    assert len(costs) == 15
    wildcard = next(
        record
        for record in costs
        if record["entity_key"] == "diagnosis=*|facility=*|severity=*"
    )
    assert {item["key"] for item in wildcard["payload"]["metrics"]} >= {
        "median_charges",
        "p25_charges",
        "p75_charges",
        "p90_charges",
        "median_costs",
        "p25_costs",
        "p75_costs",
        "p90_costs",
        "daily_charges",
        "daily_costs",
    }


