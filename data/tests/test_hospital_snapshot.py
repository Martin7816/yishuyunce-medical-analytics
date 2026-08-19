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

from verify_hospital_snapshot import summarize_stream  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_hospital_independent_formula_on_edge_fixture():
    with EDGE_SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))

    assert raw_rows == 4
    assert scoped_rows == 3
    assert expected["facility_count"] == 2
    assert expected["options"] == [
        {"value": "F001", "label": "Hospital A"},
        {"value": "F002", "label": "Hospital B"},
    ]
    assert expected["ranking"] == [
        {"name": "Hospital A", "value": 2},
        {"name": "Hospital B", "value": 1},
    ]
    assert expected["profiles"]["F001"]["metrics"] == {
        "case_count": 2,
        "avg_los": 3.0,
        "avg_charges": 150.0,
        "avg_costs": 60.0,
        "emergency_rate": 0.5,
        "surgical_rate": 0.0,
        "severe_rate": 0.5,
    }
    assert expected["profiles"]["F002"]["metrics"] == {
        "case_count": 1,
        "avg_los": 120.0,
        "avg_charges": 0.0,
        "avg_costs": 40.0,
        "emergency_rate": 0.0,
        "surgical_rate": 1.0,
        "severe_rate": 1.0,
    }


def test_pyspark_hospital_snapshot_matches_independent_verifier(tmp_path):
    spark_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if not spark_python.exists():
        pytest.skip("workspace PySpark runtime is not installed")

    snapshot_path = tmp_path / "hospital-snapshot.json"
    environment = os.environ.copy()
    environment["PYSPARK_PYTHON"] = str(spark_python)
    command = [
        str(spark_python),
        str(DATA_ROOT / "src" / "run_full_analytics_pyspark.py"),
        "--input",
        str(EDGE_SAMPLE),
        "--output",
        str(snapshot_path),
        "--generated-at",
        "2026-08-18T08:00:00Z",
    ]
    generated = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert generated.returncode == 0, generated.stderr + generated.stdout

    verified = subprocess.run(
        [
            str(spark_python),
            str(DATA_ROOT / "src" / "verify_hospital_snapshot.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--snapshot",
            str(snapshot_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert verified.returncode == 0, verified.stderr + verified.stdout
    result = json.loads(verified.stdout)
    assert result["status"] == "PASS"
    assert result["facility_count"] == 2
    assert result["profile_count"] == 2

    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    profiles = [
        record
        for record in document["records"]
        if record["module_key"] == "hospitals"
        and record["entity_key"].startswith("profile:")
    ]
    assert profiles
    assert all(
        "case_count"
        in {metric["key"] for metric in profile["payload"]["metrics"]}
        for profile in profiles
    )
