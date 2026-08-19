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

from verify_payment_snapshot import expected_payload, summarize_stream  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_independent_payment_formula_includes_empty_combinations():
    with EDGE_SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))

    assert raw_rows == 4
    assert scoped_rows == 3
    assert expected["options"] == {
        "payment_type": ["Medicaid", "Medicare", "Self-Pay"],
        "age_group": ["0 to 17", "18 to 29", "50 to 69"],
    }
    assert len(expected["aggregates"]) == 16
    wildcard = expected["aggregates"][(None, None)]
    assert wildcard["count"] == 3
    assert wildcard["payment"] == {
        "Medicare": 1,
        "Medicaid": 1,
        "Self-Pay": 1,
    }
    assert wildcard["age"] == {
        "0 to 17": 1,
        "18 to 29": 1,
        "50 to 69": 1,
    }
    assert list(wildcard["charges"]) == [100.0, 200.0]
    assert expected_payload((None, None), wildcard, expected["options"])["metrics"] == [
        {"key": "record_count", "label": "记录数", "value": 3, "unit": "条"},
        {"key": "avg_charges", "label": "平均收费", "value": 150.0, "unit": "美元"},
        {"key": "median_charges", "label": "收费中位数", "value": 100.0, "unit": "美元"},
    ]
    assert wildcard["payment_charge_count"]["Medicaid"] == 0
    assert expected["aggregates"][("Medicaid", "50 to 69")]["count"] == 0


def test_pyspark_payment_snapshot_matches_independent_verifier(tmp_path):
    pytest.importorskip("pyspark")

    snapshot_path = tmp_path / "payment-snapshot.json"
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
            str(DATA_ROOT / "src" / "verify_payment_snapshot.py"),
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
    assert result["payment_key_count"] == 16
    assert result["empty_combination_count"] == 6
