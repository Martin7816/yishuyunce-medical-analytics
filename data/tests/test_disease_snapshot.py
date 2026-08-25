from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(DATA_ROOT / "src"))

from verify_disease_snapshot import empty_profile, profile_metrics, summarize_stream  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_non_disease_diagnosis_is_excluded_from_every_disease_result():
    content = """Discharge Year,Length of Stay,CCSR Diagnosis Description,CCSR Diagnosis Code
2021,1,LIVEBORN,BIRTH001
2021,2,ASTHMA,RSP009
"""

    expected, raw_rows, scoped_rows = summarize_stream(
        csv.DictReader(StringIO(content))
    )

    assert raw_rows == 2
    assert scoped_rows == 2
    assert expected["diagnosis_count"] == 1
    assert expected["options"] == [{"value": "RSP009", "label": "ASTHMA"}]
    assert expected["ranking"] == [{"name": "ASTHMA", "value": 1}]


def test_disease_independent_formula_on_edge_fixture():
    with EDGE_SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))

    assert raw_rows == 4
    assert scoped_rows == 3
    assert expected["diagnosis_count"] == 2
    assert expected["options"] == [
        {"value": "END003", "label": "DIABETES"},
        {"value": "RSP009", "label": "ASTHMA"},
    ]
    assert expected["ranking"] == [
        {"name": "ASTHMA", "value": 1},
        {"name": "DIABETES", "value": 1},
    ]
    assert expected["profiles"]["END003"]["metrics"] == {
        "record_count": 1,
        "avg_los": 120.0,
        "avg_charges": 0.0,
        "avg_costs": 40.0,
        "emergency_rate": 0.0,
        "surgical_rate": 1.0,
        "severe_rate": 1.0,
    }
    assert expected["profiles"]["RSP009"]["metrics"] == {
        "record_count": 1,
        "avg_los": 2.0,
        "avg_charges": 100.0,
        "avg_costs": 20.0,
        "emergency_rate": 1.0,
        "surgical_rate": 0.0,
        "severe_rate": 1.0,
    }
    assert expected["profiles"]["END003"]["sections"]["hospitals"] == [
        {"name": "Hospital B", "value": 1}
    ]


def test_disease_severe_rate_excludes_unknown_severity_from_denominator():
    profile = empty_profile()
    profile["count"] = 2
    profile["severe_yes"] = 1
    profile["severity_valid_count"] = 1

    assert profile_metrics(profile)["severe_rate"] == 1.0


def test_disease_rates_exclude_missing_indicator_fields_from_denominators():
    profile = empty_profile()
    profile["count"] = 3
    profile["emergency_yes"] = 1
    profile["emergency_valid_count"] = 1
    profile["surgical_yes"] = 1
    profile["surgical_valid_count"] = 2

    metrics = profile_metrics(profile)

    assert metrics["emergency_rate"] == 1.0
    assert metrics["surgical_rate"] == 0.5


def test_pyspark_disease_snapshot_matches_independent_verifier(tmp_path):
    pytest.importorskip("pyspark")

    snapshot_path = tmp_path / "disease-snapshot.json"
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
            str(DATA_ROOT / "src" / "verify_disease_snapshot.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--snapshot",
            str(snapshot_path),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert verified.returncode == 0, verified.stderr + verified.stdout
    result = json.loads(verified.stdout)
    assert result["status"] == "PASS"
    assert result["diagnosis_count"] == 2
    assert result["profile_count"] == 2
    assert result["empty_profile_count"] == 0
