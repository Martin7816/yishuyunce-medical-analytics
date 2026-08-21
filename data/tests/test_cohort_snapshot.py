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

from verify_cohort_snapshot import summarize_stream  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_independent_cohort_formulas_include_empty_combinations():
    with EDGE_SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))

    assert raw_rows == 4
    assert scoped_rows == 3
    assert expected["options"] == {
        "age_group": ["0 to 17", "18 to 29", "50 to 69"],
        "gender": ["F", "M"],
        "admission_type": ["Elective", "Emergency"],
    }

    aggregates = expected["aggregates"]
    assert len(aggregates) == 36
    assert aggregates[(None, None, None)]["count"] == 3
    assert aggregates[("0 to 17", "F", "Emergency")]["count"] == 1
    assert aggregates[("50 to 69", "M", "Emergency")]["count"] == 1
    assert aggregates[("18 to 29", "F", "Emergency")]["count"] == 0
    assert aggregates[(None, None, None)]["emergency_yes"] == 1
    assert aggregates[(None, None, None)]["severity_valid_count"] == 2
    assert aggregates[(None, None, None)]["los"] == [2, 120, 4]


def test_pyspark_cohort_snapshot_matches_independent_verifier(tmp_path):
    runtimes = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        DATA_ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    spark_python = next((path for path in runtimes if path.exists()), None)
    if spark_python is None:
        pytest.skip("workspace PySpark runtime is not installed")

    snapshot_path = tmp_path / "cohort-snapshot.json"
    environment = os.environ.copy()
    environment["PYSPARK_PYTHON"] = str(spark_python)
    generated = subprocess.run(
        [
            str(spark_python),
            str(DATA_ROOT / "src" / "run_full_analytics_pyspark.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--output",
            str(snapshot_path),
            "--generated-at",
            "2026-08-18T08:00:00Z",
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
            str(spark_python),
            str(DATA_ROOT / "src" / "verify_cohort_snapshot.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--snapshot",
            str(snapshot_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert verified.returncode == 0, verified.stderr + verified.stdout
    result = json.loads(verified.stdout)
    assert result["status"] == "PASS"
    assert result["cohort_key_count"] == 36
    assert result["empty_combination_count"] == 16
